"""Stock quantities: balance every product to its target, then derive both balance sources.

This runs after all rows exist, including the rows the traps add. Only opening
rows, purchases and transfers get their quantities here. Every other row keeps
the quantity it was generated with.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from generator import config
from generator.common import distribute_integer

KNOWN_BALANCE_DEPOTS = ("1", "2")
"""The depot balance source only has columns for these two depots (T12)."""


def _set_transfer_quantities(movements: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Sizes every transfer pair so the destination depot covers its outbound lines.

    Returns:
        One row per product and destination depot with the stock left there.
    """
    is_transfer = movements["flow"] == "transfer"
    transfer_in = movements[is_transfer & (movements["direction"] == "G")]
    outbound = movements[~is_transfer & (movements["direction"] == "C")]
    depot_outbound = outbound.groupby(["product_code", "depot_code"])["quantity"].sum().rename("depot_outbound")

    destinations = transfer_in.groupby(["product_code", "depot_code"]).size().rename("pairs").reset_index()
    destinations = destinations.merge(depot_outbound.reset_index(), on=["product_code", "depot_code"], how="left")
    destinations["depot_outbound"] = destinations["depot_outbound"].fillna(0).astype(np.int64)
    buffer = np.where(destinations["depot_code"] == "3",
                      rng.integers(config.DEPOT_3_STOCK_RANGE[0], config.DEPOT_3_STOCK_RANGE[1] + 1, len(destinations)),
                      rng.integers(config.BRANCH_BUFFER_RANGE[0], config.BRANCH_BUFFER_RANGE[1] + 1, len(destinations)))
    destinations["transfer_total"] = np.maximum(destinations["depot_outbound"] + buffer, destinations["pairs"])
    destinations["end_stock"] = destinations["transfer_total"] - destinations["depot_outbound"]

    group_keys = transfer_in["product_code"] + "|" + transfer_in["depot_code"]
    totals = pd.Series(destinations["transfer_total"].to_numpy(),
                       index=destinations["product_code"] + "|" + destinations["depot_code"])
    pair_quantity = pd.Series(distribute_integer(group_keys, totals, rng), index=transfer_in["doc_key"].to_numpy())
    movements.loc[is_transfer, "quantity"] = movements.loc[is_transfer, "doc_key"].map(pair_quantity).to_numpy()
    return destinations


def balance_quantities(movements: pd.DataFrame, roles: pd.DataFrame,
                       rng: np.random.Generator) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Sets opening, purchase and transfer quantities so each product hits its target stock.

    Most products end the year with positive stock. The T10 control group ends
    at exactly 0, and the T11 "both negative" group ends below 0.

    Args:
        movements: All movement lines.
        roles: Product roles.
        rng: Random generator.

    Returns:
        The movements with final quantities, and one row of stock targets per product.

    Raises:
        RuntimeError: If an exact target cannot be reached or the result does not add up.
    """
    movements = movements.reset_index(drop=True).copy()
    destinations = _set_transfer_quantities(movements, rng)
    is_transfer = movements["flow"] == "transfer"
    is_outbound = (movements["direction"] == "C") & ~is_transfer
    is_other_inbound = (movements["direction"] == "G") & ~movements["flow"].isin(["opening", "purchase", "transfer"])

    frame = roles.set_index("product_code")
    index = frame.index
    outbound = movements[is_outbound].groupby("product_code")["quantity"].sum().reindex(index, fill_value=0).to_numpy()
    other_in = movements[is_other_inbound].groupby("product_code")["quantity"].sum().reindex(index, fill_value=0).to_numpy()
    purchases = movements[movements["flow"] == "purchase"].groupby("product_code").size().reindex(index, fill_value=0).to_numpy()
    has_opening = movements.loc[movements["flow"] == "opening", "product_code"].drop_duplicates()
    has_opening = index.isin(has_opening)
    depot_end = destinations.pivot_table(index="product_code", columns="depot_code", values="end_stock",
                                         aggfunc="sum", fill_value=0)
    depot_2_end = depot_end.get("2", pd.Series(dtype=np.int64)).reindex(index, fill_value=0).to_numpy()
    depot_3_end = depot_end.get("3", pd.Series(dtype=np.int64)).reindex(index, fill_value=0).to_numpy()
    role = frame["role"].to_numpy()
    n = len(frame)

    # Targets: positive for most products, exact for the control groups.
    ending = np.maximum(1, np.round(outbound * rng.uniform(*config.ENDING_STOCK_SHARE, n))).astype(np.int64)
    ending = np.maximum(ending, depot_2_end + depot_3_end + 1)
    ending = np.where(role == "t10_zero_balance_control", 0, ending)
    low, high = config.BOTH_NEGATIVE_RANGE
    ending = np.where(role == "t11d_both_negative", -rng.integers(low, high + 1, n), ending)
    opening = np.where(has_opening,
                       np.maximum(1, np.round(outbound * rng.uniform(*config.OPENING_STOCK_SHARE, n))), 0)
    opening = opening.astype(np.int64)

    no_purchase = purchases == 0
    opening_only = no_purchase & has_opening
    opening = np.where(opening_only, np.maximum(1, ending + outbound - other_in), opening)
    ending = np.where(opening_only, opening + other_in - outbound, ending)
    ending = np.where(no_purchase & ~has_opening, other_in - outbound, ending)

    # Every purchase line needs at least 1 unit. Normal products absorb a
    # shortfall in their ending stock. Exact-target products first lower their
    # opening stock, then sell a little more instead.
    purchase_total = ending + outbound - opening - other_in
    shortfall = np.where(no_purchase, 0, np.maximum(0, purchases - purchase_total))
    exact = np.isin(role, list(config.EXACT_STOCK_ROLES))
    reducible = np.where(has_opening, opening - 1, 0)
    reduce = np.where(exact, np.minimum(shortfall, reducible), 0)
    opening = opening - reduce
    shortfall = shortfall - reduce
    extra_outbound = np.where(exact, shortfall, 0)
    ending = np.where(exact, ending, ending + shortfall)
    outbound = outbound + extra_outbound
    purchase_total = np.where(no_purchase, 0, ending + outbound - opening - other_in)

    extra = pd.Series(extra_outbound, index=index)
    extra = extra[extra > 0]
    if not extra.empty:
        candidates = movements[is_outbound & movements["product_code"].isin(extra.index)]
        largest = candidates.groupby("product_code")["quantity"].idxmax()
        if len(largest) != len(extra):
            raise RuntimeError("An exact-target product has no outbound line to adjust.")
        movements.loc[largest.to_numpy(), "quantity"] += extra.reindex(largest.index).to_numpy()

    is_purchase = movements["flow"] == "purchase"
    movements.loc[is_purchase, "quantity"] = distribute_integer(
        movements.loc[is_purchase, "product_code"], pd.Series(purchase_total, index=index), rng)
    is_opening = movements["flow"] == "opening"
    movements.loc[is_opening, "quantity"] = (movements.loc[is_opening, "product_code"]
                                             .map(pd.Series(opening, index=index)).to_numpy())

    targets = pd.DataFrame({
        "product_code": index,
        "role": role,
        "ending_stock": ending,
        "depot_2_stock": depot_2_end,
        "depot_3_stock": depot_3_end,
    })
    truth = stock_by_depot(movements).groupby("product_code")["quantity"].sum()
    moved = targets[targets["product_code"].isin(truth.index)]
    if (truth.reindex(moved["product_code"]).to_numpy() != moved["ending_stock"].to_numpy()).any():
        raise RuntimeError("Stock balancing did not reach the targets.")
    return movements, targets


def stock_by_depot(movements: pd.DataFrame) -> pd.DataFrame:
    """Returns the signed stock per product and depot: inbound adds, outbound subtracts."""
    signed = np.where(movements["direction"] == "G", movements["quantity"], -movements["quantity"])
    frame = pd.DataFrame({
        "product_code": movements["product_code"].to_numpy(),
        "depot_code": movements["depot_code"].to_numpy(),
        "quantity": signed,
    })
    return frame.groupby(["product_code", "depot_code"], as_index=False)["quantity"].sum()


def build_balance_sources(movements: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Derives the two clean balance sources from the movements.

    The balance view holds one total per product that has moved. The depot
    balance source hardcodes two depot columns, so depot 3 is simply lost (T12).

    Args:
        movements: All movement lines with final quantities.

    Returns:
        The balance view and the depot balance source.
    """
    by_depot = stock_by_depot(movements)
    balance_view = (by_depot.groupby("product_code")["quantity"].sum()
                    .rename("balance_qty").reset_index())
    known = by_depot[by_depot["depot_code"].isin(KNOWN_BALANCE_DEPOTS)]
    depot_balance = (known.pivot_table(index="product_code", columns="depot_code", values="quantity",
                                       aggfunc="sum", fill_value=0)
                     .reindex(columns=list(KNOWN_BALANCE_DEPOTS), fill_value=0)
                     .rename(columns={"1": "depot_1_qty", "2": "depot_2_qty"})
                     .reset_index())
    depot_balance.columns.name = None
    return balance_view, depot_balance
