"""The clean world: one fiscal year of stock movements that obey every rule.

Nothing in this module is a trap. When a role needs a product to have no rows
of some kind (for example "no purchase at all"), the world simply leaves those
rows out. The trap modules add the rows that break naive SQL later.

Quantities of opening rows, purchases and transfers stay 0 here. The stock
module sets them at the end, so every product reaches its target stock.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from generator import config
from generator.catalog import real_customers
from generator.common import (
    allocate_counts,
    business_days,
    price_decimals,
    price_level,
    random_days,
    random_days_before,
    rng_for,
    split_into_documents,
    to_price_units,
    weighted_choice,
    weighted_options,
)

LINE_COLUMNS = [
    "product_code", "movement_date", "doc_key", "series", "movement_type", "direction", "document_type",
    "quantity", "price_units", "currency", "account_code", "depot_code", "flow", "entry_lag_days",
]
POOL_COLUMNS = ["product_code", "currency", "popularity", "group_code", "list_price", "dealer_price"]


def make_lines(**columns: object) -> pd.DataFrame:
    """Builds movement lines in the shared column layout.

    Series are converted to arrays first, so rows line up by position and
    never by index. Scalars are broadcast.

    Args:
        **columns: One value or array per column in ``LINE_COLUMNS``.
            ``account_code`` and ``entry_lag_days`` are optional.

    Returns:
        A DataFrame with the ``LINE_COLUMNS`` layout.
    """
    columns.setdefault("account_code", None)
    columns.setdefault("entry_lag_days", pd.NA)
    values = {name: (value.to_numpy() if isinstance(value, (pd.Series, pd.Index)) else value)
              for name, value in columns.items()}
    frame = pd.DataFrame(values)
    frame["movement_date"] = pd.to_datetime(frame["movement_date"]).astype("datetime64[ns]")
    frame["quantity"] = frame["quantity"].astype(np.int64)
    frame["price_units"] = frame["price_units"].astype(np.int64)
    frame["entry_lag_days"] = frame["entry_lag_days"].astype("Int64")
    return frame[LINE_COLUMNS]


def sequence_keys(prefix: str, count: int) -> pd.Series:
    """Returns internal document keys like ``prefix000001``."""
    return prefix + pd.Series(np.arange(1, count + 1)).astype(str).str.zfill(6)


def sale_pool(products: pd.DataFrame, roles: pd.DataFrame) -> pd.DataFrame:
    """Returns the products that can be sold: every product that has movements."""
    role = products["product_code"].map(roles.set_index("product_code")["role"])
    return products.loc[~role.isin(config.NO_MOVEMENT_ROLES), POOL_COLUMNS].reset_index(drop=True)


def branch_codes(roles: pd.DataFrame) -> np.ndarray:
    """Returns the products that are also stocked in the branch depot."""
    return roles.loc[roles["is_branch"], "product_code"].to_numpy()


def cost_at(frame: pd.DataFrame) -> np.ndarray:
    """Returns the underlying unit cost of each row's product at the row's date."""
    return (frame["list_price"].to_numpy() * frame["cost_ratio"].to_numpy()
            * price_level(frame["movement_date"], frame["currency"]))


def purchase_price_units(frame: pd.DataFrame, is_dealer: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Returns stored purchase prices: cost with supplier noise, dealer markup where relevant."""
    noise = 1 + rng.uniform(-config.PURCHASE_PRICE_NOISE, config.PURCHASE_PRICE_NOISE, len(frame))
    price = cost_at(frame) * np.where(is_dealer, config.DEALER_PURCHASE_MARKUP, 1.0) * noise
    return to_price_units(price, price_decimals(frame["currency"], rng))


def sale_price_units(frame: pd.DataFrame, price_basis: str, rng: np.random.Generator) -> np.ndarray:
    """Returns stored sale prices: per unit, VAT-exclusive, net of discount (T14).

    Args:
        frame: Lines with list price, dealer price, currency, date and account discount.
        price_basis: "list" (customers), "dealer" (dealer price) or "retail" (no discounts).
        rng: Random generator.

    Returns:
        An int64 array of price units.
    """
    base = frame["dealer_price"] if price_basis == "dealer" else frame["list_price"]
    level = price_level(frame["movement_date"], frame["currency"])
    if price_basis == "retail":
        account_discount = np.zeros(len(frame))
        line_discount = np.zeros(len(frame))
    else:
        account_discount = frame["discount"].to_numpy()
        line_discount = weighted_options(config.LINE_DISCOUNTS, len(frame), rng)
    price = base.to_numpy() * level * (1 - account_discount) * (1 - line_discount)
    return to_price_units(price, price_decimals(frame["currency"], rng))


def quantities(groups: pd.Series, multiplier: float, max_quantity: int | None,
               rng: np.random.Generator) -> np.ndarray:
    """Draws skewed line quantities: mostly small, sometimes large."""
    mean = groups.map(config.MEAN_LINE_QUANTITY).to_numpy() * multiplier
    shape = 1.5
    quantity = 1 + rng.poisson(rng.gamma(shape, (mean - 1) / shape))
    if max_quantity is not None:
        quantity = np.minimum(quantity, max_quantity)
    return quantity.astype(np.int64)


def outbound_depots(product_codes: pd.Series, branch: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Ships branch products from depot 2 part of the time; everything else from depot 1."""
    from_branch = product_codes.isin(branch).to_numpy() & (rng.random(len(product_codes)) < config.BRANCH_OUTBOUND_SHARE)
    return np.where(from_branch, "2", "1")


def fill_document_lines(documents: pd.DataFrame, pool: pd.DataFrame, rng: np.random.Generator,
                        cover_pool: bool = False) -> pd.DataFrame:
    """Picks distinct products for every document, from the pool of the document's currency.

    Args:
        documents: One row per document with ``doc_key``, ``currency`` and ``n_lines``.
        pool: Sellable products with currency and popularity.
        rng: Random generator.
        cover_pool: If True, every pool product gets at least one line. Each
            product is placed first in a random document of its currency.

    Returns:
        One row per line with ``doc_key`` and ``product_code``.

    Raises:
        RuntimeError: If a document could not be filled with distinct products.
    """
    parts = []
    for currency, docs in documents.groupby("currency", sort=True):
        candidates = pool[pool["currency"] == currency]
        weights = candidates["popularity"].to_numpy()
        doc_keys = np.repeat(docs["doc_key"].to_numpy(), docs["n_lines"].to_numpy() * 4)
        random_draws = pd.DataFrame({
            "doc_key": doc_keys,
            "product_code": rng.choice(candidates["product_code"].to_numpy(), len(doc_keys), p=weights / weights.sum()),
        })
        frames = [random_draws]
        if cover_pool:
            frames.insert(0, pd.DataFrame({
                "doc_key": rng.choice(docs["doc_key"].to_numpy(), len(candidates), replace=False),
                "product_code": candidates["product_code"].to_numpy(),
            }))
        drawn = pd.concat(frames, ignore_index=True).drop_duplicates()
        drawn["slot"] = drawn.groupby("doc_key", sort=False).cumcount()
        drawn = drawn.merge(docs[["doc_key", "n_lines"]], on="doc_key")
        parts.append(drawn[drawn["slot"] < drawn["n_lines"]])
    lines = pd.concat(parts, ignore_index=True)
    filled = lines.groupby("doc_key").size().reindex(documents["doc_key"], fill_value=0).to_numpy()
    if (filled != documents["n_lines"].to_numpy()).any():
        raise RuntimeError("A document could not be filled with distinct products.")
    return lines[["doc_key", "product_code"]]


def outbound_lines(*, flow: str, accounts: pd.DataFrame, total_lines: int, lines_per_document: tuple[float, int],
                   pool: pd.DataFrame, branch: np.ndarray, series: str, movement_type: str,
                   document_types: dict[str, float], price_basis: str, rng: np.random.Generator,
                   quantity_multiplier: float = 1.0, max_quantity: int | None = None, doc_prefix: str,
                   start: object = None, end: object = None, cover_pool: bool = False) -> pd.DataFrame:
    """Builds outbound documents (sales, open sales, internal adjustments).

    Every document has one account, one date, one currency and one document
    type. Its lines are distinct products of that currency.

    Args:
        flow: Internal flow label for the lines.
        accounts: Accounts to draw from, with ``activity_weight`` and ``discount``.
        total_lines: Exact number of lines to build.
        lines_per_document: Mean and maximum lines per document.
        pool: Sellable products.
        branch: Products also stocked in depot 2.
        series: Document series of the lines.
        movement_type: ERP movement type (J or H).
        document_types: Document type codes with their weights.
        price_basis: "list", "dealer" or "retail".
        rng: Random generator.
        quantity_multiplier: Scales the mean line quantity.
        max_quantity: Optional cap on line quantity.
        doc_prefix: Prefix for internal document keys.
        start: Optional first allowed date.
        end: Optional last allowed date.
        cover_pool: If True, every pool product is sold at least once.

    Returns:
        Movement lines.
    """
    mean_lines, max_lines = lines_per_document
    counts = split_into_documents(total_lines, mean_lines, max_lines, rng)
    currency_weight = pool.groupby("currency")["popularity"].sum()
    documents = pd.DataFrame({
        "doc_key": sequence_keys(doc_prefix, len(counts)).to_numpy(),
        "account_code": weighted_choice(accounts["account_code"], accounts["activity_weight"], len(counts), rng),
        "movement_date": random_days(rng, len(counts), start, end),
        "currency": weighted_choice(currency_weight.index, currency_weight.to_numpy(), len(counts), rng),
        "document_type": weighted_choice(list(document_types), list(document_types.values()), len(counts), rng),
        "n_lines": counts,
    })
    lines = (fill_document_lines(documents, pool, rng, cover_pool)
             .merge(documents.drop(columns="n_lines"), on="doc_key")
             .merge(pool.drop(columns="currency"), on="product_code")
             .merge(accounts[["account_code", "discount"]], on="account_code"))
    return make_lines(
        product_code=lines["product_code"],
        movement_date=lines["movement_date"],
        doc_key=lines["doc_key"],
        series=series,
        movement_type=movement_type,
        direction="C",
        document_type=lines["document_type"],
        quantity=quantities(lines["group_code"], quantity_multiplier, max_quantity, rng),
        price_units=sale_price_units(lines, price_basis, rng),
        currency=lines["currency"],
        account_code=lines["account_code"],
        depot_code=outbound_depots(lines["product_code"], branch, rng),
        flow=flow,
    )


def delivery_days(account_codes: np.ndarray, weekdays: tuple[int, ...], days_per_account: int,
                  rng: np.random.Generator) -> pd.DataFrame:
    """Gives each supplier or dealer its own set of distinct delivery days."""
    pool = business_days(pd.Timestamp(config.YEAR_START) + pd.Timedelta(days=1),
                         config.LAST_REGULAR_PURCHASE_DATE, weekdays)
    picks = np.argsort(rng.random((len(account_codes), len(pool))), axis=1)[:, :days_per_account]
    return pd.DataFrame({
        "account_code": np.repeat(account_codes, days_per_account),
        "movement_date": pool.values[picks.ravel()],
    })


def last_purchase_dates(movements: pd.DataFrame) -> pd.Series:
    """Returns the date of the last purchase row per product."""
    purchases = movements[movements["flow"] == "purchase"]
    return purchases.groupby("product_code")["movement_date"].max()


def regular_purchases(products: pd.DataFrame, accounts: pd.DataFrame, roles: pd.DataFrame,
                      rng: np.random.Generator) -> pd.DataFrame:
    """Builds purchase invoice lines (J + G + 2).

    Suppliers deliver on Monday to Thursday and dealers on Friday. Each product
    has one supplier and at most one dealer, so a product never has two regular
    purchases on the same date. Same-date ties are left to the T4 trap.
    """
    role = products["product_code"].map(roles.set_index("product_code")["role"])
    buyers = products[~role.isin(config.NO_REGULAR_PURCHASE_ROLES)].reset_index(drop=True)
    suppliers = accounts.loc[accounts["account_class"] == "supplier", "account_code"].to_numpy()
    dealers = accounts.loc[accounts["account_class"] == "dealer", "account_code"].to_numpy()
    days = pd.concat([
        delivery_days(suppliers, config.SUPPLIER_DELIVERY_WEEKDAYS, config.SUPPLIER_DELIVERY_DAYS, rng),
        delivery_days(dealers, config.DEALER_DELIVERY_WEEKDAYS, config.DEALER_DELIVERY_DAYS, rng),
    ])
    sources = pd.concat([
        buyers[["product_code", "supplier_code"]].rename(columns={"supplier_code": "account_code"}),
        buyers.loc[buyers["dealer_code"].notna(), ["product_code", "dealer_code"]]
        .rename(columns={"dealer_code": "account_code"}),
    ])
    candidates = sources.merge(days, on="account_code")
    caps = candidates.groupby("product_code").size().reindex(buyers["product_code"]).to_numpy()
    world_total = (config.LINE_TOTALS["purchase"] - config.PRODUCT_ROLES["t04_same_date_tie"]
                   - config.PRODUCT_ROLES["t03d_priority_over_date"])
    counts = allocate_counts(world_total, np.sqrt(buyers["popularity"].to_numpy()), caps, rng)
    candidates["order"] = rng.random(len(candidates))
    candidates["rank"] = candidates.groupby("product_code")["order"].rank(method="first") - 1
    candidates = candidates.merge(pd.DataFrame({"product_code": buyers["product_code"], "n_lines": counts}),
                                  on="product_code")
    chosen = (candidates[candidates["rank"] < candidates["n_lines"]]
              .merge(products, on="product_code")
              .sort_values(["product_code", "movement_date"])
              .reset_index(drop=True))
    series = chosen["account_code"].map(accounts.set_index("account_code")["invoice_series"])
    return make_lines(
        product_code=chosen["product_code"],
        movement_date=chosen["movement_date"],
        doc_key="PUR|" + chosen["account_code"] + "|" + chosen["movement_date"].dt.strftime("%Y-%m-%d"),
        series=series,
        movement_type="J",
        direction="G",
        document_type="2",
        quantity=0,
        price_units=purchase_price_units(chosen, chosen["account_code"].isin(dealers).to_numpy(), rng),
        currency=chosen["currency"],
        account_code=chosen["account_code"],
        depot_code="1",
        flow="purchase",
    )


def pending_waybills(products: pd.DataFrame, accounts: pd.DataFrame, purchases: pd.DataFrame,
                     rng: np.random.Generator) -> pd.DataFrame:
    """Builds December purchase waybills that are not invoiced yet (N + G, no price)."""
    buyers = products[products["product_code"].isin(purchases["product_code"])].reset_index(drop=True)
    chosen = buyers.iloc[rng.choice(len(buyers), config.LINE_TOTALS["pending_waybill"], replace=False)]
    chosen = chosen.reset_index(drop=True)
    dates = pd.Series(random_days(rng, len(chosen), start=pd.Timestamp(config.FISCAL_YEAR, 12, 1)))
    series = chosen["supplier_code"].map(accounts.set_index("account_code")["waybill_series"])
    return make_lines(
        product_code=chosen["product_code"],
        movement_date=dates,
        doc_key="PWB|" + chosen["supplier_code"] + "|" + dates.dt.strftime("%Y-%m-%d"),
        series=series,
        movement_type="N",
        direction="G",
        document_type="4",
        quantity=rng.integers(1, 20, len(chosen)),
        price_units=0,
        currency=chosen["currency"],
        account_code=chosen["supplier_code"],
        depot_code="1",
        flow="pending_waybill",
    )


def _eligible_for_returns(products: pd.DataFrame, purchases: pd.DataFrame) -> pd.DataFrame:
    """Returns products that have room for a priced inbound row before their last purchase."""
    last = last_purchase_dates(purchases).rename("last_purchase").reset_index()
    eligible = products.merge(last, on="product_code")
    return eligible[eligible["last_purchase"] >= pd.Timestamp(config.RETURN_ELIGIBLE_AFTER)].reset_index(drop=True)


def customer_returns(products: pd.DataFrame, accounts: pd.DataFrame, purchases: pd.DataFrame,
                     rng: np.random.Generator) -> pd.DataFrame:
    """Builds customer return lines (L + G) dated before the product's last purchase.

    In the clean world a return never comes after the last purchase, so a
    naive "latest inbound price" still finds the purchase. T3 breaks that on purpose.
    """
    total = (config.LINE_TOTALS["customer_return"] - config.PRODUCT_ROLES["t03a_return_after_purchase"]
             - config.PRODUCT_ROLES["t03c_no_cost_source"] * config.T03C_RETURNS_PER_PRODUCT)
    eligible = _eligible_for_returns(products, purchases)
    chosen = eligible.iloc[weighted_choice(np.arange(len(eligible)), eligible["popularity"], total, rng)]
    chosen = chosen.reset_index(drop=True)
    customers = real_customers(accounts)
    chosen["movement_date"] = random_days_before(chosen["last_purchase"], rng)
    discount = rng.uniform(*config.T03A_RETURN_DISCOUNT, total)
    price = chosen["list_price"].to_numpy() * price_level(chosen["movement_date"], chosen["currency"]) * (1 - discount)
    return make_lines(
        product_code=chosen["product_code"],
        movement_date=chosen["movement_date"],
        doc_key=sequence_keys("RTN|", total),
        series=config.OWN_SERIES["return"],
        movement_type="L",
        direction="G",
        document_type="4",
        quantity=rng.integers(1, config.RETURN_MAX_QUANTITY + 1, total),
        price_units=to_price_units(price, price_decimals(chosen["currency"], rng)),
        currency=chosen["currency"],
        account_code=weighted_choice(customers["account_code"], customers["activity_weight"], total, rng),
        depot_code="1",
        flow="customer_return",
    )


def dealer_returns(products: pd.DataFrame, accounts: pd.DataFrame, purchases: pd.DataFrame,
                   rng: np.random.Generator) -> pd.DataFrame:
    """Builds dealer returns in both directions (T9 world rows).

    L + G: a dealer returns goods we sold to it (priced at the dealer price).
    L + C: we return goods we bought from a dealer (priced at our purchase price).
    """
    dealers = accounts[accounts["account_class"] == "dealer"]
    eligible = _eligible_for_returns(products, purchases)
    total_in = config.LINE_TOTALS["dealer_return_in"]
    returned_in = eligible.iloc[weighted_choice(np.arange(len(eligible)), eligible["popularity"], total_in, rng)]
    returned_in = returned_in.reset_index(drop=True)
    returned_in["movement_date"] = random_days_before(returned_in["last_purchase"], rng)
    price_in = (returned_in["dealer_price"].to_numpy()
                * price_level(returned_in["movement_date"], returned_in["currency"]))
    inbound = make_lines(
        product_code=returned_in["product_code"],
        movement_date=returned_in["movement_date"],
        doc_key=sequence_keys("DRI|", total_in),
        series=config.OWN_SERIES["return"],
        movement_type="L",
        direction="G",
        document_type="4",
        quantity=rng.integers(1, config.RETURN_MAX_QUANTITY + 1, total_in),
        price_units=to_price_units(price_in, price_decimals(returned_in["currency"], rng)),
        currency=returned_in["currency"],
        account_code=weighted_choice(dealers["account_code"], dealers["activity_weight"], total_in, rng),
        depot_code="1",
        flow="dealer_return_in",
    )

    total_out = config.LINE_TOTALS["dealer_return_out"]
    sourced = products[products["dealer_code"].notna()
                       & products["product_code"].isin(purchases["product_code"])].reset_index(drop=True)
    returned_out = sourced.iloc[weighted_choice(np.arange(len(sourced)), sourced["popularity"], total_out, rng)]
    returned_out = returned_out.reset_index(drop=True)
    returned_out["movement_date"] = random_days(rng, total_out)
    outbound = make_lines(
        product_code=returned_out["product_code"],
        movement_date=returned_out["movement_date"],
        doc_key=sequence_keys("DRO|", total_out),
        series=config.OWN_SERIES["purchase_return"],
        movement_type="L",
        direction="C",
        document_type="3",
        quantity=rng.integers(1, config.RETURN_MAX_QUANTITY + 1, total_out),
        price_units=purchase_price_units(returned_out, np.ones(total_out, dtype=bool), rng),
        currency=returned_out["currency"],
        account_code=returned_out["dealer_code"],
        depot_code="1",
        flow="dealer_return_out",
    )
    return pd.concat([inbound, outbound], ignore_index=True)


def transfer_lines(product_codes: np.ndarray, destination_depot: str, dates: np.ndarray, doc_prefix: str,
                   products: pd.DataFrame) -> pd.DataFrame:
    """Builds depot transfer pairs (B + C out of depot 1, B + G into the destination)."""
    count = len(product_codes)
    currency = pd.Series(product_codes).map(products.set_index("product_code")["currency"]).to_numpy()
    keys = sequence_keys(doc_prefix, count).to_numpy()
    common = {
        "product_code": np.concatenate([product_codes, product_codes]),
        "movement_date": np.concatenate([dates, dates]),
        "doc_key": np.concatenate([keys, keys]),
        "series": config.OWN_SERIES["transfer"],
        "movement_type": "B",
        "document_type": "6",
        "quantity": 0,
        "price_units": 0,
        "currency": np.concatenate([currency, currency]),
        "flow": "transfer",
        "entry_lag_days": 0,
    }
    return make_lines(
        **common,
        direction=np.repeat(["C", "G"], count),
        depot_code=np.repeat(["1", destination_depot], count),
    )


def branch_transfers(products: pd.DataFrame, roles: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Builds the transfers that stock the branch depot (depot 2)."""
    codes = np.repeat(np.sort(branch_codes(roles)), config.TRANSFERS_PER_BRANCH_PRODUCT)
    return transfer_lines(codes, "2", random_days(rng, len(codes)), "TRF|", products)


def opening_rows(products: pd.DataFrame, roles: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Builds opening-balance rows (A + G), carried over from the prior year."""
    role = products["product_code"].map(roles.set_index("product_code")["role"])
    openers = products[~role.isin(config.NO_OPENING_ROLES)].reset_index(drop=True)
    openers["movement_date"] = pd.Timestamp(config.YEAR_START)
    price = cost_at(openers) * config.OPENING_PRICE_FACTOR
    return make_lines(
        product_code=openers["product_code"],
        movement_date=openers["movement_date"],
        doc_key="OPENING",
        series=config.OWN_SERIES["opening"],
        movement_type="A",
        direction="G",
        document_type="0",
        quantity=0,
        price_units=to_price_units(price, price_decimals(openers["currency"], rng)),
        currency=openers["currency"],
        depot_code="1",
        flow="opening",
    )


def build_world(products: pd.DataFrame, accounts: pd.DataFrame, roles: pd.DataFrame) -> pd.DataFrame:
    """Builds all clean-world movement lines.

    Args:
        products: Product master with purchase sources.
        accounts: Chart of accounts.
        roles: Product roles.

    Returns:
        Movement lines without insert keys or document numbers.
    """
    pool = sale_pool(products, roles)
    branch = branch_codes(roles)
    customers = real_customers(accounts)
    dealers = accounts[accounts["account_class"] == "dealer"]
    collectors = accounts[accounts["account_class"] == "collector"]
    sale_series = config.OWN_SERIES["sale_invoice"]
    waybill_series = config.OWN_SERIES["sale_waybill"]

    purchases = regular_purchases(products, accounts, roles, rng_for("world.purchases"))
    parts = [
        opening_rows(products, roles, rng_for("world.opening")),
        purchases,
        pending_waybills(products, accounts, purchases, rng_for("world.pending_waybills")),
        outbound_lines(flow="sale_invoice", accounts=customers, total_lines=config.SALE_INVOICE_LINES["customer"],
                       lines_per_document=config.LINES_PER_DOCUMENT["customer"], pool=pool, branch=branch,
                       series=sale_series, movement_type="J", document_types={"1": 1.0}, price_basis="list",
                       doc_prefix="SIV|C|", cover_pool=True, rng=rng_for("world.sales.customer")),
        outbound_lines(flow="sale_invoice", accounts=dealers, total_lines=config.SALE_INVOICE_LINES["dealer"],
                       lines_per_document=config.LINES_PER_DOCUMENT["dealer"], pool=pool, branch=branch,
                       series=sale_series, movement_type="J", document_types={"1": 1.0}, price_basis="dealer",
                       quantity_multiplier=config.DEALER_QUANTITY_MULTIPLIER, doc_prefix="SIV|D|",
                       rng=rng_for("world.sales.dealer")),
        outbound_lines(flow="sale_invoice", accounts=collectors, total_lines=config.SALE_INVOICE_LINES["collector"],
                       lines_per_document=config.LINES_PER_DOCUMENT["collector"], pool=pool, branch=branch,
                       series=sale_series, movement_type="J", document_types={"1": 1.0}, price_basis="retail",
                       max_quantity=config.COLLECTOR_MAX_QUANTITY, doc_prefix="SIV|R|",
                       rng=rng_for("world.sales.collector")),
        outbound_lines(flow="open_sale", accounts=customers, total_lines=config.OPEN_SALE_LINES["customer"],
                       lines_per_document=config.LINES_PER_DOCUMENT["open_sale"], pool=pool, branch=branch,
                       series=waybill_series, movement_type="H", document_types=config.OPEN_SALE_DOCUMENT_TYPES,
                       price_basis="list", doc_prefix="SWB|C|", rng=rng_for("world.open_sales.customer")),
        outbound_lines(flow="open_sale", accounts=collectors, total_lines=config.OPEN_SALE_LINES["collector"],
                       lines_per_document=config.LINES_PER_DOCUMENT["collector"], pool=pool, branch=branch,
                       series=waybill_series, movement_type="H", document_types=config.OPEN_SALE_DOCUMENT_TYPES,
                       price_basis="retail", max_quantity=config.COLLECTOR_MAX_QUANTITY, doc_prefix="SWB|R|",
                       rng=rng_for("world.open_sales.collector")),
        customer_returns(products, accounts, purchases, rng_for("world.customer_returns")),
        dealer_returns(products, accounts, purchases, rng_for("world.dealer_returns")),
        branch_transfers(products, roles, rng_for("world.transfers")),
    ]
    return pd.concat(parts, ignore_index=True)
