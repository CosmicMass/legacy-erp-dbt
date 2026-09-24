"""Stock traps T10, T11 and T12: the two balance sources are not the truth.

T12 adds movement rows (a third depot). T10 and T11 change the balance sources
after they are derived from the movements.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from generator import config
from generator.catalog import real_customers
from generator.common import (
    manifest_rows,
    price_decimals,
    price_level,
    random_days,
    to_price_units,
    weighted_choice,
    weighted_options,
)
from generator.roles import role_codes
from generator.stock import stock_by_depot
from generator.world import make_lines, quantities, sequence_keys, transfer_lines


def plant_t12_third_depot(movements: pd.DataFrame, products: pd.DataFrame, accounts: pd.DataFrame,
                          roles: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """T12: stocks a third depot that the depot balance source does not know about.

    Depot 3 opened in the last quarter. It receives transfers from depot 1 and
    ships a few sales. Its stock never shows up in the two-column depot source.
    """
    codes = role_codes(roles, "t12_depot_3_stock")
    extra_pairs = rng.choice(codes, config.T12_TRANSFER_PAIRS - len(codes))
    pair_codes = np.sort(np.concatenate([codes, extra_pairs]))
    last_transfer_day = pd.Timestamp(config.YEAR_END) - pd.Timedelta(days=16)
    dates = random_days(rng, len(pair_codes), start=config.DEPOT_3_OPENING_DATE, end=last_transfer_day)
    transfers = transfer_lines(pair_codes, "3", dates, "TRF|D3|", products)

    sold = products.set_index("product_code").loc[np.resize(rng.permutation(codes), config.T12_SALE_LINES)]
    sold = sold.reset_index()
    sold["movement_date"] = random_days(rng, len(sold), start=pd.Timestamp(config.DEPOT_3_OPENING_DATE)
                                        + pd.Timedelta(days=14))
    customers = real_customers(accounts)
    account_codes = weighted_choice(customers["account_code"], customers["activity_weight"], len(sold), rng)
    discount = pd.Series(account_codes).map(customers.set_index("account_code")["discount"]).to_numpy()
    line_discount = weighted_options(config.LINE_DISCOUNTS, len(sold), rng)
    price = (sold["list_price"].to_numpy() * price_level(sold["movement_date"], sold["currency"])
             * (1 - discount) * (1 - line_discount))
    sales = make_lines(
        product_code=sold["product_code"],
        movement_date=sold["movement_date"],
        doc_key=sequence_keys("SIV|D3|", len(sold)),
        series=config.OWN_SERIES["sale_invoice"],
        movement_type="J",
        direction="C",
        document_type="1",
        quantity=quantities(sold["group_code"], 1.0, 10, rng),
        price_units=to_price_units(price, price_decimals(sold["currency"], rng)),
        currency=sold["currency"],
        account_code=account_codes,
        depot_code="3",
        flow="sale_invoice",
    )
    return pd.concat([movements, transfers, sales], ignore_index=True)


def register_t12_third_depot(movements: pd.DataFrame) -> pd.DataFrame:
    """T12: records the depot codes in movements and the stock that sits in depot 3."""
    by_depot = stock_by_depot(movements)
    depot_3 = by_depot[(by_depot["depot_code"] == "3") & (by_depot["quantity"] != 0)]
    depot_codes = ",".join(sorted(movements["depot_code"].unique()))
    return pd.concat([
        manifest_rows("T12", "T12_depot_codes", "metric", ["depot_codes_in_movements"], [depot_codes],
                      "The depot balance source only has columns for depots 1 and 2."),
        manifest_rows("T12", "T12_depot_3_stock", "product", depot_3["product_code"], depot_3["quantity"],
                      "Stock in depot 3; missing from the depot balance source. Expected value: depot 3 stock."),
    ], ignore_index=True)


def plant_t10_missing_from_balance(balance_view: pd.DataFrame, targets: pd.DataFrame,
                                   roles: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """T10: removes products that hold stock from the balance view entirely.

    Also records the control group: products present in the view with a
    balance of exactly 0. Absent and zero are different findings.
    """
    missing = role_codes(roles, "t10_missing_from_balance")
    zero = role_codes(roles, "t10_zero_balance_control")
    stock = targets.set_index("product_code")["ending_stock"]
    manifest = pd.concat([
        manifest_rows("T10", "T10a_missing_from_balance", "product", missing, stock.reindex(missing).to_numpy(),
                      "Holds stock but has no row in the balance view. Expected value: true stock."),
        manifest_rows("T10", "T10b_zero_balance_control", "product", zero, "0",
                      "Present in the balance view with a balance of 0."),
    ], ignore_index=True)
    return balance_view[~balance_view["product_code"].isin(missing)].reset_index(drop=True), manifest


def plant_t11_source_disagreements(balance_view: pd.DataFrame, depot_balance: pd.DataFrame, roles: pd.DataFrame,
                                   rng: np.random.Generator) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """T11: makes the balance view and the depot source disagree in three distinct ways.

    (a) The depot total is negative while the balance is positive and higher.
    (b) The depot shows stock that the balance does not show.
    (c) Other mismatches, including a negative balance with positive depot stock.
    (d) Control group: both sources agree on a negative figure.

    Args:
        balance_view: Balance view, one total per product.
        depot_balance: Depot source with two depot columns.
        roles: Product roles.
        rng: Random generator.

    Returns:
        The changed balance view, the changed depot source and the manifest rows.
    """
    balance = balance_view.set_index("product_code")["balance_qty"].copy()
    depots = depot_balance.set_index("product_code")[["depot_1_qty", "depot_2_qty"]].copy()

    case_a = role_codes(roles, "t11a_depot_negative")
    deficit = rng.integers(config.T11A_DEPOT_DEFICIT_RANGE[0], config.T11A_DEPOT_DEFICIT_RANGE[1] + 1, len(case_a))
    depots.loc[case_a, "depot_1_qty"] = -deficit - depots.loc[case_a, "depot_2_qty"].to_numpy()

    case_b = role_codes(roles, "t11b_depot_higher")
    true_b = balance.loc[case_b].to_numpy()
    balance.loc[case_b] = true_b - (1 + np.floor(rng.random(len(case_b)) * true_b)).astype(np.int64)

    case_c = role_codes(roles, "t11c_other_mismatch")
    low, high = config.T11C_BALANCE_EXCESS_RANGE
    balance.loc[case_c[:2]] += rng.integers(low, high + 1, 2)
    low, high = config.T11C_DEPOT_EXCESS_RANGE
    depots.loc[case_c[2:4], "depot_2_qty"] += rng.integers(low, high + 1, 2)
    low, high = config.T11C_NEGATIVE_BALANCE_RANGE
    balance.loc[case_c[4:]] = -rng.integers(low, high + 1, len(case_c[4:]))

    case_d = role_codes(roles, "t11d_both_negative")
    depot_total = depots.sum(axis=1)
    notes = {
        "T11a_depot_negative": "Depot total negative, balance positive and higher.",
        "T11b_depot_higher": "Depot shows stock that the balance does not show.",
        "T11c_other_mismatch": "Other disagreement between the two sources.",
        "T11d_both_negative": "Both sources agree on a negative figure (control group).",
    }
    parts = []
    for case_id, codes in (("T11a_depot_negative", case_a), ("T11b_depot_higher", case_b),
                           ("T11c_other_mismatch", case_c), ("T11d_both_negative", case_d)):
        values = ("balance=" + balance.reindex(codes).astype(str) + ";depot_total="
                  + depot_total.reindex(codes).astype(str))
        parts.append(manifest_rows("T11", case_id, "product", codes, values.to_numpy(), notes[case_id]))

    balance_view = balance.rename("balance_qty").reset_index()
    depot_balance = depots.reset_index()
    return balance_view, depot_balance, pd.concat(parts, ignore_index=True)
