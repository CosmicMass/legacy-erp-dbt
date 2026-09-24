"""Raw ERP-style tables and the CSV writer.

Raw seeds keep the ERP's cryptic column names. Every value is text. Every
non-null value is quoted, so leading and trailing spaces (T15) survive any CSV
reader, and an empty unquoted field always means NULL.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from generator import config
from generator.common import MANIFEST_COLUMNS, format_fixed

ZERO_PRICE = "0.00000000"


def _date_text(dates: pd.Series) -> pd.Series:
    """Formats dates as ISO text."""
    return dates.dt.strftime("%Y-%m-%d")


def _int_text(values: pd.Series) -> pd.Series:
    """Formats integers as text."""
    return values.astype("int64").astype(str)


def to_raw_tables(products: pd.DataFrame, accounts: pd.DataFrame, movements: pd.DataFrame,
                  balance_view: pd.DataFrame, depot_balance: pd.DataFrame, ledger: pd.DataFrame,
                  manifest: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Converts the generator frames into raw seed tables with ERP column names.

    Args:
        products: Product master.
        accounts: Chart of accounts.
        movements: Movement lines with insert keys and document numbers.
        balance_view: Balance view.
        depot_balance: Depot balance source.
        ledger: Account ledger.
        manifest: Trap manifest.

    Returns:
        Seed name to table, every column as text.
    """
    products = products.sort_values("product_code").reset_index(drop=True)
    accounts = accounts.sort_values("account_code").reset_index(drop=True)
    movements = movements.sort_values("insert_key").reset_index(drop=True)
    balance_view = balance_view.sort_values("product_code").reset_index(drop=True)
    depot_balance = depot_balance.sort_values("product_code").reset_index(drop=True)
    ledger = ledger.sort_values(["movement_date", "document_number"]).reset_index(drop=True)
    manifest = manifest.sort_values(["trap_id", "case_id", "entity_key"], key=_natural_trap_order).reset_index(drop=True)

    return {
        "raw_tblstsabit": pd.DataFrame({
            "STOK_KODU": products["product_code"],
            "STOK_ADI": products["product_name"],
            "GRUP_KODU": products["group_code"],
            "KOD_1": products["category_code"],
            "MARKA": products["brand"],
            "SATIS_FIAT1": format_fixed(products["list_price_cents"], 2),
            "SATIS_FIAT2": format_fixed(products["dealer_price_cents"], 2),
            "SATIS_DOV_TIP": products["master_currency"].map(config.MASTER_CURRENCY_CODES),
        }),
        "raw_tblcasabit": pd.DataFrame({
            "CARI_KOD": accounts["account_code"],
            "CARI_ISIM": accounts["account_name"],
        }),
        "raw_tblsthar": pd.DataFrame({
            "INCKEYNO": _int_text(movements["insert_key"]),
            "STOK_KODU": movements["product_code"],
            "STHAR_TARIH": _date_text(movements["movement_date"]),
            "FISNO": movements["document_number"],
            "STHAR_HTUR": movements["movement_type"],
            "STHAR_GCKOD": movements["direction"],
            "STHAR_FTIRSIP": movements["document_type"],
            "STHAR_GCMIK": _int_text(movements["quantity"]),
            "STHAR_DOVFIAT": format_fixed(movements["price_units"], 8),
            "STHAR_DOVTIP": movements["currency"].map(config.MOVEMENT_CURRENCY_CODES),
            "STHAR_CARIKOD": movements["account_code"],
            "DEPO_KODU": movements["depot_code"],
            "STHAR_KDV": str(config.VAT_RATE_PERCENT),
            "STHAR_MALIYET": ZERO_PRICE,
            "STHAR_ORT_MALIYET": ZERO_PRICE,
        }),
        "raw_vw_stok_bakiye": pd.DataFrame({
            "STOK_KODU": balance_view["product_code"],
            "BAKIYE": _int_text(balance_view["balance_qty"]),
        }),
        "raw_vw_depo_bakiye": pd.DataFrame({
            "STOK_KODU": depot_balance["product_code"],
            "DEPO1_BAKIYE": _int_text(depot_balance["depot_1_qty"]),
            "DEPO2_BAKIYE": _int_text(depot_balance["depot_2_qty"]),
        }),
        "raw_tblcahar": pd.DataFrame({
            "CARI_KOD": ledger["account_code"],
            "FISNO": ledger["document_number"],
            "TARIH": _date_text(ledger["movement_date"]),
            "DOV_TUTAR": format_fixed(ledger["amount_cents"], 2),
            "DOVTIP": ledger["currency"].map(config.LEDGER_CURRENCY_CODES),
        }),
        "trap_manifest": manifest[MANIFEST_COLUMNS],
    }


def _natural_trap_order(column: pd.Series) -> pd.Series:
    """Sorts T2 before T10 by padding the trap number."""
    if column.name == "trap_id":
        return column.str[1:].astype(int)
    return column


def _quote(values: pd.Series) -> pd.Series:
    """Quotes every non-null value and writes NULL as an empty, unquoted field."""
    is_null = values.isna()
    text = values.where(~is_null, "").astype(str)
    quoted = '"' + text.str.replace('"', '""', regex=False) + '"'
    return quoted.where(~is_null, "")


def write_csv(table: pd.DataFrame, path: Path) -> None:
    """Writes a table as UTF-8 CSV with LF line endings, byte-identical on every run.

    Args:
        table: Table to write; every column is text.
        path: Target file.
    """
    columns = list(table.columns)
    body = _quote(table[columns[0]])
    for column in columns[1:]:
        body = body + "," + _quote(table[column])
    content = ",".join(columns) + "\n" + "\n".join(body.tolist()) + "\n"
    path.write_bytes(content.encode("utf-8"))


def write_tables(tables: dict[str, pd.DataFrame], directory: Path) -> None:
    """Writes every table to ``<directory>/<name>.csv``."""
    directory.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        write_csv(table.reset_index(drop=True), directory / f"{name}.csv")
