"""Account traps T6 to T9: who is really a customer.

T6 and T8 describe the clean world (prefix rules, collector accounts), so they
only register facts. T7 plants internal counter-accounts that look exactly
like customers. T9 registers the two-way dealer returns of the clean world.
"""

from __future__ import annotations

import pandas as pd

from generator import config
from generator.common import manifest_rows, rng_for
from generator.world import branch_codes, outbound_lines, sale_pool

SALE_FLOWS = ("sale_invoice", "open_sale")
CLASS_GROUPS = {
    "end_customer": ("customer", "legacy_customer"),
    "collector": ("collector",),
    "dealer": ("dealer",),
    "internal": ("internal",),
}


def plant_t07_internal_accounts(accounts: pd.DataFrame, movements: pd.DataFrame, products: pd.DataFrame,
                                roles: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """T7: adds internal counter-accounts under 120- and their outbound H + C rows.

    The rows are identical to real open sales: same movement type, same
    direction, same document series, document types 3 and 4, and a sale-level
    price. Only the account tells them apart.

    Args:
        accounts: Chart of accounts.
        movements: Movement lines.
        products: Product master.
        roles: Product roles.

    Returns:
        The accounts and the movements, both extended.
    """
    internal = pd.DataFrame({
        "account_code": [account.code for account in config.INTERNAL_ACCOUNTS],
        "account_name": [account.name for account in config.INTERNAL_ACCOUNTS],
        "segment": [account.code.split("-")[1] for account in config.INTERNAL_ACCOUNTS],
        "account_class": "internal",
        "discount": 0.0,
        "activity_weight": 1.0,
        "series_offset": 1,
    })
    accounts = pd.concat([accounts, internal], ignore_index=True).sort_values("account_code").reset_index(drop=True)
    pool = sale_pool(products, roles)
    branch = branch_codes(roles)
    parts = [movements]
    for account in config.INTERNAL_ACCOUNTS:
        if account.lines == 0:
            continue
        parts.append(outbound_lines(
            flow="internal_adjustment", accounts=internal[internal["account_code"] == account.code],
            total_lines=account.lines, lines_per_document=config.LINES_PER_DOCUMENT["internal"], pool=pool,
            branch=branch, series=config.OWN_SERIES["sale_waybill"], movement_type="H",
            document_types=config.INTERNAL_DOCUMENT_TYPES, price_basis="list",
            doc_prefix=f"INT|{account.code}|", rng=rng_for(f"t07.{account.code}"),
        ))
    return accounts, pd.concat(parts, ignore_index=True)


def register_t07_structural_signal(accounts: pd.DataFrame) -> pd.DataFrame:
    """T7: records the internal accounts and the real customers the structural signal also flags.

    The signal: a 120- segment with very few accounts. It finds every internal
    account, but it also flags real customers that happen to sit in a small
    segment. It is a detector, not a classifier.
    """
    customers_120 = accounts[accounts["account_code"].str.startswith("120-")]
    segment_size = customers_120.groupby("segment")["account_code"].transform("size")
    flagged = customers_120[segment_size <= config.STRUCTURAL_SEGMENT_MAX_SIZE]
    internal = accounts.loc[accounts["account_class"] == "internal"].merge(
        pd.DataFrame({"account_code": [a.code for a in config.INTERNAL_ACCOUNTS],
                      "created_year": [a.created_year for a in config.INTERNAL_ACCOUNTS],
                      "lines": [a.lines for a in config.INTERNAL_ACCOUNTS]}), on="account_code")
    false_positive = flagged[flagged["account_class"] != "internal"]
    size_of = segment_size.groupby(customers_120["segment"]).first()
    return pd.concat([
        manifest_rows("T7", "T7a_internal_account", "account", internal["account_code"], internal["lines"],
                      "Created " + internal["created_year"].astype(str) + "; segment size "
                      + internal["segment"].map(size_of).astype(str)
                      + ". Expected value: outbound H+C lines this year."),
        manifest_rows("T7", "T7b_structural_false_positive", "account", false_positive["account_code"], None,
                      "Real customer in a small segment (size "
                      + false_positive["segment"].map(size_of).astype(str) + "); flagged by the signal."),
    ], ignore_index=True)


def _account_class_map(accounts: pd.DataFrame) -> pd.Series:
    """Maps account code to its reporting class group."""
    group_of_class = {cls: group for group, classes in CLASS_GROUPS.items() for cls in classes}
    return accounts.set_index("account_code")["account_class"].map(group_of_class)


def register_t06_sales_by_class(movements: pd.DataFrame, accounts: pd.DataFrame) -> pd.DataFrame:
    """T6: records sale lines and quantities per account class.

    Sell-through counts end customers only (120- and A... without internal
    accounts and collectors). Dealer sales are real sales but not end-customer sales.
    """
    sales = movements[movements["flow"].isin(SALE_FLOWS + ("internal_adjustment",))]
    group = sales["account_code"].map(_account_class_map(accounts))
    summary = sales.groupby(group.to_numpy())["quantity"].agg(["size", "sum"]).reindex(list(CLASS_GROUPS),
                                                                                     fill_value=0)
    dealers = accounts.loc[accounts["account_class"] == "dealer", "account_code"]
    bought_from = movements.loc[movements["flow"] == "purchase", "account_code"]
    sold_to = movements.loc[movements["flow"] == "sale_invoice", "account_code"]
    bidirectional = int((dealers.isin(bought_from) & dealers.isin(sold_to)).sum())
    keys = ([f"sale_lines_{name}" for name in summary.index] + [f"sale_quantity_{name}" for name in summary.index]
            + ["bidirectional_dealers"])
    values = list(summary["size"]) + list(summary["sum"]) + [bidirectional]
    return manifest_rows("T6", "T6_sales_by_account_class", "metric", keys, values,
                         "H+C and J+C+1 lines. Internal rows are H+C only and are not sales.")


def register_t08_collectors(movements: pd.DataFrame, accounts: pd.DataFrame) -> pd.DataFrame:
    """T8: records collector accounts and their sale line counts. They are real sales."""
    collectors = accounts.loc[accounts["account_class"] == "collector", "account_code"]
    sales = movements[movements["flow"].isin(SALE_FLOWS)]
    lines = sales.groupby("account_code").size().reindex(collectors, fill_value=0)
    return manifest_rows("T8", "T8_collector_account", "account", collectors, lines.to_numpy(),
                         "Anonymous walk-in buyers: real revenue, no identifiable end customer. "
                         "Expected value: sale lines.")


def register_t09_dealer_returns(movements: pd.DataFrame) -> pd.DataFrame:
    """T9: records return row counts by account side and direction."""
    returns = movements[movements["movement_type"] == "L"]
    dealer_side = returns["account_code"].str.startswith(("320-", "S"))
    counts = {
        "dealer_return_rows_inbound": int((dealer_side & (returns["direction"] == "G")).sum()),
        "dealer_return_rows_outbound": int((dealer_side & (returns["direction"] == "C")).sum()),
        "customer_return_rows_inbound": int((~dealer_side & (returns["direction"] == "G")).sum()),
        "customer_return_rows_outbound": int((~dealer_side & (returns["direction"] == "C")).sum()),
    }
    return manifest_rows("T9", "T9_dealer_returns", "metric", counts.keys(), counts.values(),
                         "L rows on 320-/S accounts go both ways; customer L rows are inbound only.")
