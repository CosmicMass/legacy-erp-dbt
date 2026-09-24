"""Document numbers, line numbers and insert keys.

The insert key (INCKEYNO) follows the order in which rows were typed into the
ERP, not the document date. Some documents are entered days after their date,
and the opening rows are entered late in January. So "latest by insert key" is
not "latest by date": the date decides, and the insert key only breaks ties (T4).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from generator import config


def assign_document_numbers(movements: pd.DataFrame, accounts: pd.DataFrame) -> pd.DataFrame:
    """Numbers every document as ``<series><year><9 digits>``, in date order per series.

    Our own series start at 1. A supplier's series starts at its own offset,
    because we only see a slice of the supplier's numbering.

    Args:
        movements: Movement lines with ``doc_key`` and ``series``.
        accounts: Chart of accounts with series offsets.

    Returns:
        The movements with a ``document_number`` column.
    """
    documents = (movements.groupby("doc_key", sort=False)
                 .agg(series=("series", "first"), movement_date=("movement_date", "min"))
                 .reset_index()
                 .sort_values(["series", "movement_date", "doc_key"]))
    partners = accounts.dropna(subset=["invoice_series"])
    offsets = pd.concat([
        pd.Series(partners["series_offset"].to_numpy(), index=partners["invoice_series"].to_numpy()),
        pd.Series(partners["series_offset"].to_numpy(), index=partners["waybill_series"].to_numpy()),
    ])
    start = documents["series"].map(offsets).fillna(1).astype(np.int64)
    sequence = documents.groupby("series").cumcount() + start
    documents["document_number"] = (documents["series"] + str(config.FISCAL_YEAR)
                                    + sequence.astype(str).str.zfill(9))
    if documents["document_number"].duplicated().any():
        raise RuntimeError("Document numbers are not unique.")
    return movements.merge(documents[["doc_key", "document_number"]], on="doc_key", how="left")


def assign_insert_keys(movements: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Assigns line numbers and a monotonic insert key in entry order.

    Args:
        movements: Movement lines.
        rng: Random generator.

    Returns:
        The movements sorted by insert key, with ``line_no``, ``entry_date`` and
        ``insert_key`` columns.
    """
    movements = movements.copy()
    movements["line_no"] = movements.groupby("doc_key", sort=False).cumcount() + 1
    documents = (movements.groupby("doc_key", sort=False)
                 .agg(movement_date=("movement_date", "first"), flow=("flow", "first"),
                      preset_lag=("entry_lag_days", "first"))
                 .reset_index())
    n = len(documents)
    random_lag = np.where(rng.random(n) < config.BACKDATED_SHARE,
                          rng.integers(1, config.BACKDATED_MAX_DAYS + 1, n), 0)
    lag = documents["preset_lag"].fillna(pd.Series(random_lag)).astype(np.int64)
    entry_date = documents["movement_date"] + pd.to_timedelta(lag, unit="D")
    documents["entry_date"] = entry_date.where(documents["flow"] != "opening",
                                               pd.Timestamp(config.OPENING_ENTRY_DATE))
    documents["entry_order"] = rng.random(n)
    movements = (movements.merge(documents[["doc_key", "entry_date", "entry_order"]], on="doc_key")
                 .sort_values(["entry_date", "entry_order", "line_no"])
                 .reset_index(drop=True))
    movements["insert_key"] = np.arange(1, len(movements) + 1, dtype=np.int64)
    return movements.drop(columns="entry_order")
