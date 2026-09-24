"""Document traps T1, T2, T14 and T16. They describe the clean world, so they only register facts."""

from __future__ import annotations

import pandas as pd

from generator import config
from generator.common import PRICE_SCALE, format_fixed, manifest_rows
from generator.ledger import invoice_total_cents


def register_t01_open_sales(movements: pd.DataFrame) -> pd.DataFrame:
    """T1: open sales (H + C) are real sales that are never invoiced.

    A model that counts only J sales loses them. H and J never share a document number.
    """
    open_sales = movements[movements["flow"] == "open_sale"]
    invoices = movements[movements["flow"] == "sale_invoice"]
    h_numbers = set(movements.loc[movements["movement_type"] == "H", "document_number"])
    j_numbers = set(movements.loc[movements["movement_type"] == "J", "document_number"])
    metrics = {
        "open_sale_lines": len(open_sales),
        "open_sale_documents": open_sales["document_number"].nunique(),
        "sale_invoice_lines": len(invoices),
        "sale_invoice_documents": invoices["document_number"].nunique(),
        "documents_shared_by_h_and_j": len(h_numbers & j_numbers),
    }
    return manifest_rows("T1", "T1_open_sales", "metric", metrics.keys(), metrics.values(),
                         "Sales = J+C+1 lines plus H+C lines on real customer and collector accounts.")


def register_t02_zero_cost_columns(movements: pd.DataFrame) -> pd.DataFrame:
    """T2: the cost-named columns are 0 on every row; the real cost is the purchase FX price."""
    metrics = {"movement_rows": len(movements), "rows_with_nonzero_cost_columns": 0}
    return manifest_rows("T2", "T2_zero_cost_columns", "metric", metrics.keys(), metrics.values(),
                         "STHAR_MALIYET and STHAR_ORT_MALIYET are written as 0 on every row.")


def register_t14_ledger(ledger: pd.DataFrame) -> pd.DataFrame:
    """T14: every sale invoice reconciles to its ledger row, to the cent."""
    metrics = {"sale_invoices_in_ledger": len(ledger), "invoices_not_reconciling": 0}
    return manifest_rows("T14", "T14_ledger_reconciliation", "metric", metrics.keys(), metrics.values(),
                         f"Ledger amount = round(sum(quantity x unit price) x (1 + {config.VAT_RATE_PERCENT}/100), 2).")


def register_t16_display_precision(movements: pd.DataFrame, ledger: pd.DataFrame) -> pd.DataFrame:
    """T16: invoices whose total differs when recomputed from 2-decimal display prices.

    The expected value is the ledger amount; the note gives the display-based total.
    """
    invoices = movements[movements["flow"] == "sale_invoice"]
    display_units = (invoices["price_units"] + PRICE_SCALE // 200) // (PRICE_SCALE // 100) * (PRICE_SCALE // 100)
    display_total = invoice_total_cents(invoices["quantity"], display_units, invoices["document_number"],
                                        config.VAT_RATE_PERCENT)
    amounts = ledger.set_index("document_number")["amount_cents"]
    display_total = display_total.reindex(amounts.index)
    differs = amounts[display_total.to_numpy() != amounts.to_numpy()]
    display_text = format_fixed(display_total.reindex(differs.index).to_numpy(), 2)
    return manifest_rows("T16", "T16_display_precision_gap", "document", differs.index,
                         format_fixed(differs.to_numpy(), 2).to_numpy(),
                         ("Recomputed from 2-decimal display prices: " + display_text).to_numpy())
