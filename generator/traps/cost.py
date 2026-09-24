"""Cost traps T3, T4 and T5: rows that make a naive "latest cost" query wrong.

The correct rule: the latest cost is the FX unit price of the most recent
purchase row (J + G + 2). If there is none, use the opening row (A + G). Order
by priority, then date descending, then insert key descending. Returns and the
undocumented H + G + 4 rows are never a cost.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from generator import config
from generator.catalog import real_customers
from generator.common import (
    allocate_counts,
    format_fixed,
    manifest_rows,
    price_decimals,
    price_level,
    random_days,
    random_days_after,
    random_days_before,
    to_price_units,
    weighted_choice,
)
from generator.roles import role_codes
from generator.world import cost_at, last_purchase_dates, make_lines, sequence_keys

COST_CASES = (
    ("T3", "T3a_return_after_purchase", "t03a_return_after_purchase",
     "The latest inbound row with a price is a customer return; the cost is the latest purchase."),
    ("T3", "T3b_opening_fallback", "t03b_opening_fallback",
     "No purchase this year; the cost falls back to the opening row."),
    ("T3", "T3c_no_cost_source", "t03c_no_cost_source",
     "Only customer returns; there is no cost source, so the cost must be NULL."),
    ("T3", "T3d_priority_over_date", "t03d_priority_over_date",
     "Purchase and opening row share 1 January and the opening row has the higher insert key; priority decides."),
    ("T4", "T4_same_date_tie", "t04_same_date_tie",
     "Two purchases on the latest purchase date; the higher insert key wins."),
    ("T5", "T5a_adjustment_latest", "t05a_adjustment_latest",
     "The latest inbound row with a price is H+G+4; it is a reference figure, not a cost."),
    ("T5", "T5b_adjustment_only", "t05b_adjustment_only",
     "Only H+G+4 rows; the cost must be NULL and H+G+4 is a reference figure only."),
)


def _customer_accounts(accounts: pd.DataFrame, size: int, rng: np.random.Generator) -> np.ndarray:
    """Draws real customer accounts by activity."""
    customers = real_customers(accounts)
    return weighted_choice(customers["account_code"], customers["activity_weight"], size, rng)


def _return_lines(frame: pd.DataFrame, accounts: pd.DataFrame, doc_prefix: str,
                  rng: np.random.Generator) -> pd.DataFrame:
    """Builds customer return lines priced at sale level for the given products and dates."""
    discount = rng.uniform(*config.T03A_RETURN_DISCOUNT, len(frame))
    price = frame["list_price"].to_numpy() * price_level(frame["movement_date"], frame["currency"]) * (1 - discount)
    return make_lines(
        product_code=frame["product_code"],
        movement_date=frame["movement_date"],
        doc_key=sequence_keys(doc_prefix, len(frame)),
        series=config.OWN_SERIES["return"],
        movement_type="L",
        direction="G",
        document_type="4",
        quantity=rng.integers(1, config.RETURN_MAX_QUANTITY + 1, len(frame)),
        price_units=to_price_units(price, price_decimals(frame["currency"], rng)),
        currency=frame["currency"],
        account_code=_customer_accounts(accounts, len(frame), rng),
        depot_code="1",
        flow="customer_return",
    )


def plant_t03a_return_after_purchase(movements: pd.DataFrame, products: pd.DataFrame, accounts: pd.DataFrame,
                                     roles: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """T3a: adds one customer return dated after the product's last purchase.

    A query that ranks inbound rows by date alone now returns the return price,
    which is a sale-level price and not a cost.
    """
    codes = role_codes(roles, "t03a_return_after_purchase")
    last = last_purchase_dates(movements).reindex(codes)
    frame = products.set_index("product_code").loc[codes].reset_index()
    frame["movement_date"] = random_days_after(last, rng)
    return pd.concat([movements, _return_lines(frame, accounts, "RTN|T3A|", rng)], ignore_index=True)


def plant_t03c_no_cost_source(movements: pd.DataFrame, products: pd.DataFrame, accounts: pd.DataFrame,
                              roles: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """T3c: products with customer returns only, and no purchase or opening row."""
    codes = np.repeat(role_codes(roles, "t03c_no_cost_source"), config.T03C_RETURNS_PER_PRODUCT)
    frame = products.set_index("product_code").loc[codes].reset_index()
    frame["movement_date"] = random_days(rng, len(frame))
    return pd.concat([movements, _return_lines(frame, accounts, "RTN|T3C|", rng)], ignore_index=True)


def plant_t03d_priority_over_date(movements: pd.DataFrame, products: pd.DataFrame, accounts: pd.DataFrame,
                                  roles: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """T3d: the only purchase is dated 1 January, the same date as the opening row.

    The opening rows are entered late in January, so they get the higher insert
    key. Ordering by date, then insert key, picks the opening row. Only ordering
    by priority first picks the purchase.
    """
    codes = role_codes(roles, "t03d_priority_over_date")
    frame = products.set_index("product_code").loc[codes].reset_index()
    frame["movement_date"] = pd.Timestamp(config.YEAR_START)
    noise = 1 + rng.uniform(-config.PURCHASE_PRICE_NOISE, config.PURCHASE_PRICE_NOISE, len(frame))
    series = frame["supplier_code"].map(accounts.set_index("account_code")["invoice_series"])
    rows = make_lines(
        product_code=frame["product_code"],
        movement_date=frame["movement_date"],
        doc_key="PUR|" + frame["supplier_code"] + "|" + frame["movement_date"].dt.strftime("%Y-%m-%d"),
        series=series,
        movement_type="J",
        direction="G",
        document_type="2",
        quantity=0,
        price_units=to_price_units(cost_at(frame) * noise, price_decimals(frame["currency"], rng)),
        currency=frame["currency"],
        account_code=frame["supplier_code"],
        depot_code="1",
        flow="purchase",
        entry_lag_days=0,
    )
    return pd.concat([movements, rows], ignore_index=True)


def plant_t04_same_date_tie(movements: pd.DataFrame, roles: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """T4: adds a second purchase row on the product's latest purchase date.

    Some ties sit in the same document (a second line), others in a second
    document from the same supplier on the same day. Prices are set later by
    ``finalize_t04_prices``, once the insert keys exist.
    """
    codes = role_codes(roles, "t04_same_date_tie")
    purchases = movements[(movements["flow"] == "purchase") & movements["product_code"].isin(codes)]
    latest = purchases.sort_values(["product_code", "movement_date"]).groupby("product_code").tail(1).copy()
    same_document = rng.choice(codes, config.T04_SAME_DOCUMENT_TIES, replace=False)
    second_document = ~latest["product_code"].isin(same_document)
    latest.loc[second_document, "doc_key"] = latest.loc[second_document, "doc_key"] + "|B"
    return pd.concat([movements, latest], ignore_index=True)


def finalize_t04_prices(movements: pd.DataFrame, roles: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """T4: prices the two tied rows so the later-entered row is the true latest cost.

    For some products the winner has the higher price and for the others the
    lower price, so neither MAX nor MIN gives the right answer.
    """
    movements = movements.copy()
    codes = role_codes(roles, "t04_same_date_tie")
    higher_winners = rng.choice(codes, config.T04_WINNER_HIGHER_PRICE, replace=False)
    purchases = movements[(movements["flow"] == "purchase") & movements["product_code"].isin(codes)]
    latest_date = purchases.groupby("product_code")["movement_date"].transform("max")
    tie = purchases[purchases["movement_date"] == latest_date].sort_values(["product_code", "insert_key"])
    if (tie.groupby("product_code").size() != 2).any():
        raise RuntimeError("Every T4 product must have exactly two purchases on its latest date.")

    base = tie.groupby("product_code")["price_units"].transform("first").to_numpy()
    gap = pd.Series(rng.uniform(*config.T04_PRICE_GAP, len(codes)), index=codes)
    decimals = np.where(tie["currency"].to_numpy() == "TL", 2, config.FX_PRICE_DECIMALS)
    high = to_price_units(base / 1e8 * (1 + tie["product_code"].map(gap).to_numpy()), decimals)
    is_winner = tie.groupby("product_code").cumcount().to_numpy() == 1
    winner_is_high = tie["product_code"].isin(higher_winners).to_numpy()
    movements.loc[tie.index, "price_units"] = np.where(is_winner == winner_is_high, high, base)
    return movements


def plant_t05_customer_adjustments(movements: pd.DataFrame, products: pd.DataFrame, accounts: pd.DataFrame,
                                   roles: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """T5: adds H + G + 4 rows against customer accounts, priced a little below cost.

    The rows look like a cost because they carry an FX price on an inbound row.
    """
    last = last_purchase_dates(movements)
    latest_codes = role_codes(roles, "t05a_adjustment_latest")
    only_codes = role_codes(roles, "t05b_adjustment_only")
    background_codes = role_codes(roles, "t05_background")

    before_latest = rng.choice(latest_codes, config.T05_EXTRA_ROWS_BEFORE_LATEST)
    background_counts = allocate_counts(config.T05_BACKGROUND_ROWS, np.ones(len(background_codes)),
                                        np.full(len(background_codes), 2), rng)
    background = np.repeat(background_codes, background_counts)
    only = np.repeat(only_codes, config.T05_ROWS_PER_ADJUSTMENT_ONLY)
    parts = [
        pd.DataFrame({"product_code": latest_codes,
                      "movement_date": random_days_after(last.reindex(latest_codes), rng)}),
        pd.DataFrame({"product_code": before_latest,
                      "movement_date": random_days_before(last.reindex(before_latest), rng)}),
        pd.DataFrame({"product_code": only, "movement_date": random_days(rng, len(only))}),
        pd.DataFrame({"product_code": background,
                      "movement_date": random_days_before(last.reindex(background), rng)}),
    ]
    frame = pd.concat(parts, ignore_index=True).merge(products, on="product_code", how="left")
    price = cost_at(frame) * rng.uniform(*config.T05_PRICE_RATIO, len(frame))
    rows = make_lines(
        product_code=frame["product_code"],
        movement_date=frame["movement_date"],
        doc_key=sequence_keys("ADJ|", len(frame)),
        series=config.OWN_SERIES["sale_waybill"],
        movement_type="H",
        direction="G",
        document_type="4",
        quantity=rng.integers(1, config.ADJUSTMENT_MAX_QUANTITY + 1, len(frame)),
        price_units=to_price_units(price, price_decimals(frame["currency"], rng)),
        currency=frame["currency"],
        account_code=_customer_accounts(accounts, len(frame), rng),
        depot_code="1",
        flow="customer_adjustment",
    )
    return pd.concat([movements, rows], ignore_index=True)


def latest_cost_by_priority(movements: pd.DataFrame) -> pd.Series:
    """Applies the correct latest-cost rule. Products without a cost source get no entry.

    Args:
        movements: Movement lines with insert keys.

    Returns:
        Price units of the latest cost, indexed by product code.
    """
    is_purchase = ((movements["movement_type"] == "J") & (movements["direction"] == "G")
                   & (movements["document_type"] == "2"))
    is_opening = (movements["movement_type"] == "A") & (movements["direction"] == "G")
    candidates = movements[is_purchase | is_opening].copy()
    candidates["priority"] = np.where(is_purchase[is_purchase | is_opening], 1, 2)
    ordered = candidates.sort_values(["product_code", "priority", "movement_date", "insert_key"],
                                     ascending=[True, True, False, False])
    return ordered.groupby("product_code")["price_units"].first()


def naive_latest_inbound(movements: pd.DataFrame) -> pd.DataFrame:
    """Applies the naive rule: the latest inbound row with a price, by date then insert key."""
    inbound = movements[(movements["direction"] == "G") & (movements["price_units"] > 0)]
    ordered = inbound.sort_values(["product_code", "movement_date", "insert_key"], ascending=[True, False, False])
    return ordered.groupby("product_code")[["flow", "price_units"]].first()


def register_cost_expectations(movements: pd.DataFrame, roles: pd.DataFrame) -> pd.DataFrame:
    """Records the expected latest cost of every planted cost-trap product.

    The expected value is empty when the cost must be NULL.
    """
    latest = latest_cost_by_priority(movements)
    naive = naive_latest_inbound(movements)
    parts = []
    for trap_id, case_id, role, note in COST_CASES:
        codes = role_codes(roles, role)
        expected = latest.reindex(codes)
        expected_text = format_fixed(expected.fillna(0).to_numpy(), 8).where(expected.notna().to_numpy(), None)
        naive_price = naive["price_units"].reindex(codes)
        naive_text = format_fixed(naive_price.fillna(0).to_numpy(), 8)
        notes = (note + " Naive pick: " + naive["flow"].reindex(codes).fillna("none").to_numpy()
                 + " at " + naive_text.to_numpy())
        parts.append(manifest_rows(trap_id, case_id, "product", codes, expected_text.to_numpy(), notes))
    winners = register_t04_winner_side(movements, roles)
    manifest = pd.concat(parts, ignore_index=True)
    is_t04 = manifest["case_id"] == "T4_same_date_tie"
    manifest.loc[is_t04, "note"] = (manifest.loc[is_t04, "note"] + " Winner has the "
                                    + manifest.loc[is_t04, "entity_key"].map(winners) + " price.")
    return manifest


def register_t04_winner_side(movements: pd.DataFrame, roles: pd.DataFrame) -> pd.Series:
    """Returns "higher" or "lower" per T4 product: the winner's price compared with the other tie row."""
    codes = role_codes(roles, "t04_same_date_tie")
    purchases = movements[(movements["flow"] == "purchase") & movements["product_code"].isin(codes)]
    latest_date = purchases.groupby("product_code")["movement_date"].transform("max")
    tie = purchases[purchases["movement_date"] == latest_date].sort_values(["product_code", "insert_key"])
    prices = tie.groupby("product_code")["price_units"].agg(["first", "last"])
    return pd.Series(np.where(prices["last"] > prices["first"], "higher", "lower"), index=prices.index)
