"""The account ledger: one receivable row per sale invoice (T14).

The receivable equals the sum of quantity x stored unit price, times 1.20 for
VAT, rounded once to the cent. The math uses integers, so the result is exact.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from generator import config
from generator.common import PRICE_SCALE


def invoice_total_cents(quantity: pd.Series, price_units: pd.Series, document_number: pd.Series,
                        vat_rate_percent: int) -> pd.Series:
    """Returns the VAT-inclusive total per document, rounded half-up to the cent.

    Args:
        quantity: Line quantities.
        price_units: Stored unit prices in units of 1e-8.
        document_number: Document number per line.
        vat_rate_percent: VAT rate, for example 20.

    Returns:
        Total in cents, indexed by document number.
    """
    line_units = quantity.to_numpy(dtype=np.int64) * price_units.to_numpy(dtype=np.int64)
    net_units = pd.Series(line_units).groupby(document_number.to_numpy()).sum()
    gross = net_units * (100 + vat_rate_percent)  # units of 1e-10
    if (gross.abs() > 2**62).any():
        raise OverflowError("Invoice totals are too large for int64 math.")
    half = PRICE_SCALE // 2
    return (gross + half) // PRICE_SCALE


def build_ledger(movements: pd.DataFrame) -> pd.DataFrame:
    """Builds one ledger row per sale invoice document.

    Args:
        movements: Movement lines with document numbers and final quantities.

    Returns:
        One row per sale invoice: account, document number, date, amount in
        cents and currency.
    """
    invoices = movements[movements["flow"] == "sale_invoice"]
    headers = invoices.groupby("document_number").agg(
        account_code=("account_code", "first"),
        movement_date=("movement_date", "first"),
        currency=("currency", "first"),
        accounts=("account_code", "nunique"),
        currencies=("currency", "nunique"),
    )
    if (headers["accounts"] != 1).any() or (headers["currencies"] != 1).any():
        raise RuntimeError("A sale invoice has more than one account or currency.")
    totals = invoice_total_cents(invoices["quantity"], invoices["price_units"], invoices["document_number"],
                                 config.VAT_RATE_PERCENT)
    headers["amount_cents"] = totals.reindex(headers.index).to_numpy()
    return (headers.drop(columns=["accounts", "currencies"]).reset_index()
            .sort_values(["movement_date", "document_number"]).reset_index(drop=True))
