"""Master data of the clean world: products, accounts and purchase sources."""

from __future__ import annotations

import numpy as np
import pandas as pd

from generator import config
from generator.common import weighted_options

NAME_WORDS = (
    "ANVIL", "BEACON", "CEDAR", "COBALT", "CRESCENT", "EMBER", "FALCON", "GRANITE", "HARBOR",
    "IRONWOOD", "JUNIPER", "KEYSTONE", "LANTERN", "MAPLE", "MERIDIAN", "NORTHGATE", "OAKRIDGE",
    "PINNACLE", "QUARRY", "REDSTONE", "SABLE", "SUMMIT", "THORNFIELD", "UMBER", "VALEMONT",
    "WILLOW", "YARROW", "ZENITH", "ASTER", "BIRCHWOOD", "COPPERLINE", "DUNMORE", "ELMSTEAD",
    "FERNHILL", "GLENROCK", "HAZELTON", "INDIGO", "JASPER", "KILNWORTH", "LINDEN", "MARBLEWAY",
    "NIMBUS", "ONYX", "PEBBLEFORD", "QUILLON", "RAVENSCAR", "SLATEFORD", "TIDEWATER", "UPLAND",
    "VERDANT", "WRENFIELD", "ALDERWAY", "BASALT", "DRIFTWOOD", "FLINTRIDGE", "HERONWAY",
)
CUSTOMER_TRADES = (
    "MACHINERY", "HYDRAULICS", "AGRICULTURAL MACHINES", "CONVEYOR SYSTEMS", "TEXTILE MACHINES",
    "PUMP WORKS", "AUTO PARTS", "MINING SUPPLY", "FOOD MACHINERY", "PACKAGING SYSTEMS",
    "METAL WORKS", "GEARBOX SERVICE", "ELEVATOR SYSTEMS", "PLASTICS", "CEMENT EQUIPMENT",
)
SUPPLIER_TRADES = (
    "BEARING INDUSTRIES", "PRECISION COMPONENTS", "SEALING TECHNOLOGIES", "DRIVE SYSTEMS",
    "MOTION PARTS", "INDUSTRIAL TRADING", "POWER TRANSMISSION",
)
DEALER_TRADES = ("BEARING TRADE", "TRANSMISSION PARTS", "INDUSTRIAL SUPPLY", "MACHINE PARTS")
LEGAL_SUFFIXES = ("LTD", "INC", "CO")
SERIES_LETTERS = np.array(list("ABCDEFGHJKLMNPRSTUVYZ"))
REAL_CUSTOMER_CLASSES = ("customer", "legacy_customer")


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------
def _bearing_candidates() -> pd.DataFrame:
    """Lists generic bearing size designations that can serve as base codes."""
    deep_groove_series = {"60": 12, "62": 15, "63": 12, "68": 10, "69": 10}
    series = pd.Series(list(deep_groove_series)).repeat(
        [max_bore + 1 for max_bore in deep_groove_series.values()]).reset_index(drop=True)
    bore = series.groupby(series).cumcount()
    sizes = (series + bore.astype(str).str.zfill(2)).reset_index(drop=True)
    variants = pd.Series(["", "-2RS", "-ZZ", "-2RS-C3"])
    deep_groove = pd.DataFrame({
        "base_code": np.repeat(sizes.to_numpy(), len(variants)) + np.tile(variants.to_numpy(), len(sizes)),
        "category_code": "DG",
        "size_number": np.repeat(bore.to_numpy(), len(variants)),
    })
    other_ranges = (("302", 4, 12, "TR"), ("322", 5, 12, "TR"), ("NU2", 5, 12, "CY"),
                    ("NJ2", 5, 12, "CY"), ("12", 5, 10, "SA"), ("22", 5, 10, "SA"))
    others = pd.concat([
        pd.DataFrame({
            "base_code": [f"{prefix}{number:02d}" for number in range(low, high + 1)],
            "category_code": category,
            "size_number": np.arange(low, high + 1),
        })
        for prefix, low, high, category in other_ranges
    ])
    candidates = pd.concat([deep_groove, others], ignore_index=True)
    candidates["size_factor"] = 1 + 0.12 * candidates["size_number"]
    return candidates[["base_code", "category_code", "size_factor"]]


def _seal_candidates() -> pd.DataFrame:
    """Lists generic rotary shaft seal sizes (shaft x housing x width)."""
    shafts = np.arange(10, 125, 5)
    extras = np.array([12, 15, 17, 20, 22, 25, 30])
    widths = np.array([7, 8, 10, 12])
    shaft, extra, width = (grid.ravel() for grid in np.meshgrid(shafts, extras, widths, indexing="ij"))
    return pd.DataFrame({
        "base_code": pd.Series(shaft).astype(str) + "x" + pd.Series(shaft + extra).astype(str)
        + "x" + pd.Series(width).astype(str),
        "category_code": "OS",
        "size_factor": shaft / 30,
    })


def _belt_candidates() -> pd.DataFrame:
    """Lists generic V-belt profiles and lengths."""
    narrow_profiles = np.array(["SPZ", "SPA", "SPB", "XPZ"])
    narrow_lengths = np.arange(600, 2501, 100)
    classic_profiles = np.array(["A", "B", "Z"])
    classic_inches = np.arange(20, 81, 4)
    narrow = pd.DataFrame({
        "profile": np.repeat(narrow_profiles, len(narrow_lengths)),
        "length": np.tile(narrow_lengths, len(narrow_profiles)),
        "category_code": "NV",
    })
    narrow["size_factor"] = narrow["length"] / 1000
    classic = pd.DataFrame({
        "profile": np.repeat(classic_profiles, len(classic_inches)),
        "length": np.tile(classic_inches, len(classic_profiles)),
        "category_code": "VB",
    })
    classic["size_factor"] = classic["length"] * 25.4 / 1000
    belts = pd.concat([narrow, classic], ignore_index=True)
    belts["base_code"] = belts["profile"] + "-" + belts["length"].astype(str)
    return belts[["base_code", "category_code", "size_factor"]]


CANDIDATE_BUILDERS = {"BRG": _bearing_candidates, "SEL": _seal_candidates, "BLT": _belt_candidates}


def _group_variants(group: str) -> list[tuple[str, str | None]]:
    """Lists the (brand, material) variants a base code can have in a group."""
    brands = [brand.name for brand in config.BRANDS if group in brand.products_per_group]
    if group == "SEL":
        return [(brand, material) for brand in brands for material in config.SEAL_MATERIALS]
    return [(brand, None) for brand in brands]


def _group_products(group: str, rng: np.random.Generator) -> pd.DataFrame:
    """Builds the products of one group, including near-duplicate families (T15).

    A family is one base code (one physical size) sold as several products
    that differ only by brand or material. Every other base code is unique.

    Args:
        group: Product group code.
        rng: Random generator.

    Returns:
        One row per product with base code, category, size factor, brand and material.
    """
    candidates = CANDIDATE_BUILDERS[group]()
    capacity = {brand.name: brand.products_per_group[group] for brand in config.BRANDS
                if group in brand.products_per_group}
    family_sizes = [size for size, count in config.FAMILY_SIZES[group].items() for _ in range(count)]
    unique_count = sum(capacity.values()) - sum(family_sizes)
    picked = candidates.iloc[rng.choice(len(candidates), len(family_sizes) + unique_count, replace=False)]
    family_bases = picked.iloc[: len(family_sizes)]
    unique_bases = picked.iloc[len(family_sizes):]

    # Families: members get distinct variants, drawn by remaining brand capacity.
    variants = _group_variants(group)
    rows = []
    for base, size in zip(family_bases.to_dict("records"), family_sizes):
        chosen: list[tuple[str, str | None]] = []
        for _ in range(size):
            options = [variant for variant in variants if variant not in chosen
                       and capacity[variant[0]] > sum(1 for pick in chosen if pick[0] == variant[0])]
            weights = np.array([capacity[option[0]] for option in options], dtype=float)
            chosen.append(options[rng.choice(len(options), p=weights / weights.sum())])
        for brand, material in chosen:
            capacity[brand] -= 1
            rows.append({**base, "brand": brand, "material": material})
    families = pd.DataFrame(rows)

    # Unique base codes fill the remaining brand capacity.
    brands = np.repeat(list(capacity), list(capacity.values()))
    unique = unique_bases.reset_index(drop=True).assign(brand=rng.permutation(brands))
    if group == "SEL":
        unique["material"] = weighted_options(list(zip(config.SEAL_MATERIALS, config.SEAL_MATERIAL_WEIGHTS)),
                                              len(unique), rng)
    else:
        unique["material"] = None
    products = pd.concat([families, unique], ignore_index=True)
    products["group_code"] = group
    return products


def build_products(rng: np.random.Generator) -> pd.DataFrame:
    """Builds the clean product master.

    Args:
        rng: Random generator.

    Returns:
        One row per product. Hidden generator columns (true currency, cost ratio,
        popularity) never reach the raw seed.
    """
    products = pd.concat([_group_products(group, rng) for group in config.PRODUCT_GROUPS], ignore_index=True)
    brands = pd.DataFrame([{"brand": brand.name, "abbreviation": brand.abbreviation, "currency": brand.currency,
                            "price_factor": brand.price_factor} for brand in config.BRANDS])
    products = products.merge(brands, on="brand", how="left")

    is_seal = products["group_code"] == "SEL"
    material_part = products["material"].fillna("")
    products["product_code"] = np.where(
        is_seal,
        products["base_code"] + "-" + material_part + "-" + products["abbreviation"],
        products["base_code"] + "-" + products["abbreviation"],
    )
    products["product_name"] = (
        products["category_code"].map(config.CATEGORY_NAMES) + " " + products["base_code"]
        + np.where(is_seal, " " + material_part, "") + " " + products["brand"]
    )

    n = len(products)
    base_price = (products["category_code"].map(config.CATEGORY_BASE_PRICE_EUR) * products["size_factor"]
                  * products["price_factor"] * rng.lognormal(0.0, 0.2, n))
    base_price = np.where(products["currency"] == "TL", base_price * config.TL_PER_EUR_PRICE_FACTOR, base_price)
    products["list_price_cents"] = np.maximum(50, np.round(base_price * 100)).astype(np.int64)
    products["dealer_price_cents"] = np.round(products["list_price_cents"] * config.DEALER_PRICE_RATIO).astype(np.int64)
    products["list_price"] = products["list_price_cents"] / 100
    products["dealer_price"] = products["dealer_price_cents"] / 100
    products["cost_ratio"] = rng.uniform(*config.COST_RATIO_RANGE, n)
    products["popularity"] = np.maximum(config.MIN_POPULARITY, rng.lognormal(0.0, 0.8, n))
    products["master_currency"] = products["currency"]

    if products["product_code"].duplicated().any():
        raise RuntimeError("Product codes are not unique.")
    return products.sort_values("product_code").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------
def _customer_accounts(rng: np.random.Generator) -> pd.DataFrame:
    """Builds the 120- customer accounts in their segments, with two collectors."""
    segments = pd.Series(list(config.CUSTOMER_SEGMENTS)).repeat(
        list(config.CUSTOMER_SEGMENTS.values())).reset_index(drop=True)
    position = segments.groupby(segments).cumcount() + 1
    accounts = pd.DataFrame({
        "account_code": ("120-" + segments + "-" + position.astype(str).str.zfill(3)).to_numpy(),
        "segment": segments.to_numpy(),
        "account_class": "customer",
    })
    for segment in (key for key in config.COLLECTOR_ACCOUNTS if key != "A"):
        size = config.CUSTOMER_SEGMENTS[segment]
        code = f"120-{segment}-{rng.integers(1, size + 1):03d}"
        accounts.loc[accounts["account_code"] == code, "account_class"] = "collector"
    extra = pd.DataFrame({
        "account_code": [config.KEY_ACCOUNT_CODE, config.SHARED_SEGMENT_CUSTOMER_CODE],
        "segment": [config.KEY_ACCOUNT_CODE.split("-")[1], config.SHARED_SEGMENT_CUSTOMER_CODE.split("-")[1]],
        "account_class": "customer",
    })
    return pd.concat([accounts, extra], ignore_index=True)


def _legacy_customer_accounts(rng: np.random.Generator) -> pd.DataFrame:
    """Builds the legacy A... customer accounts, one of them a collector."""
    count = config.LEGACY_CUSTOMER_COUNT + 1
    numbers = np.sort(rng.choice(np.arange(100, 10_000), count, replace=False))
    classes = np.full(count, "legacy_customer", dtype=object)
    classes[rng.integers(count)] = "collector"
    return pd.DataFrame({
        "account_code": ("A" + pd.Series(numbers).astype(str).str.zfill(5)).to_numpy(),
        "segment": None,
        "account_class": classes,
    })


def _supplier_and_dealer_accounts(rng: np.random.Generator) -> pd.DataFrame:
    """Builds supplier and dealer accounts under 320- and the legacy S... prefix."""
    fx_brands = [brand for brand in config.BRANDS if brand.currency != "TL"]
    tl_brand = next(brand for brand in config.BRANDS if brand.currency == "TL")
    if config.TL_SUPPLIERS_UNDER_320 + config.TL_SUPPLIERS_UNDER_S != tl_brand.suppliers:
        raise ValueError("TL supplier counts do not match the TL brand.")

    fx_brand_names = np.repeat([brand.name for brand in fx_brands], [brand.suppliers for brand in fx_brands])
    foreign = pd.DataFrame({
        "account_code": [f"320-01-{number:03d}" for number in range(1, len(fx_brand_names) + 1)],
        "segment": "01",
        "account_class": "supplier",
        "brand": fx_brand_names,
    })
    domestic_classes = rng.permutation(["supplier"] * config.TL_SUPPLIERS_UNDER_320
                                       + ["dealer"] * config.DEALERS_UNDER_320)
    domestic = pd.DataFrame({
        "account_code": [f"320-02-{number:03d}" for number in range(1, len(domestic_classes) + 1)],
        "segment": "02",
        "account_class": domestic_classes,
    })
    legacy_classes = rng.permutation(["supplier"] * config.TL_SUPPLIERS_UNDER_S + ["dealer"] * config.DEALERS_UNDER_S)
    legacy_numbers = np.sort(rng.choice(np.arange(100, 10_000), len(legacy_classes), replace=False))
    legacy = pd.DataFrame({
        "account_code": ("S" + pd.Series(legacy_numbers).astype(str).str.zfill(5)).to_numpy(),
        "segment": None,
        "account_class": legacy_classes,
    })
    local = pd.concat([domestic, legacy], ignore_index=True)
    local["brand"] = np.where(local["account_class"] == "supplier", tl_brand.name, None)
    return pd.concat([foreign, local], ignore_index=True)


def _unique_names(count: int, trades: tuple[str, ...], rng: np.random.Generator) -> np.ndarray:
    """Draws distinct invented company names."""
    words = np.repeat(NAME_WORDS, len(trades) * len(LEGAL_SUFFIXES))
    trade = np.tile(np.repeat(trades, len(LEGAL_SUFFIXES)), len(NAME_WORDS))
    suffix = np.tile(LEGAL_SUFFIXES, len(NAME_WORDS) * len(trades))
    names = pd.Series(words) + " " + pd.Series(trade) + " " + pd.Series(suffix)
    return names.to_numpy()[rng.choice(len(names), count, replace=False)]


def _series_codes(count: int, rng: np.random.Generator) -> np.ndarray:
    """Draws distinct 3-letter document series that do not clash with our own series."""
    base = len(SERIES_LETTERS)
    numbers = rng.choice(base**3, count + len(config.OWN_SERIES), replace=False)
    codes = SERIES_LETTERS[numbers // base**2] + SERIES_LETTERS[(numbers // base) % base] + SERIES_LETTERS[numbers % base]
    codes = codes[~np.isin(codes, list(config.OWN_SERIES.values()))]
    return codes[:count]


def build_accounts(rng: np.random.Generator) -> pd.DataFrame:
    """Builds the clean chart of accounts (customers, suppliers, dealers, collectors).

    Internal counter-accounts are not part of the clean world. The T7 trap adds them.

    Args:
        rng: Random generator.

    Returns:
        One row per account, with hidden generator columns.
    """
    accounts = pd.concat([_customer_accounts(rng), _legacy_customer_accounts(rng),
                          _supplier_and_dealer_accounts(rng)], ignore_index=True)
    classes = accounts["account_class"]

    accounts["account_name"] = None
    for account_classes, trades in ((REAL_CUSTOMER_CLASSES, CUSTOMER_TRADES), (("supplier",), SUPPLIER_TRADES),
                                    (("dealer",), DEALER_TRADES)):
        mask = classes.isin(account_classes)
        accounts.loc[mask, "account_name"] = _unique_names(int(mask.sum()), trades, rng)
    collector_key = np.where(accounts["account_code"].str.startswith("A"), "A", accounts["segment"])
    is_collector = classes == "collector"
    accounts.loc[is_collector, "account_name"] = pd.Series(collector_key[is_collector]).map(
        config.COLLECTOR_ACCOUNTS).to_numpy()
    if accounts["account_name"].duplicated().any():
        raise RuntimeError("Account names are not unique.")

    n = len(accounts)
    accounts["discount"] = np.select(
        [classes.isin(REAL_CUSTOMER_CLASSES), classes == "dealer"],
        [weighted_options(config.CUSTOMER_DISCOUNTS, n, rng), weighted_options(config.DEALER_DISCOUNTS, n, rng)],
        default=0.0,
    )
    weight = rng.lognormal(0.0, 1.0, n)
    weight = np.where(classes == "legacy_customer", weight * 0.6, weight)
    weight = np.where(accounts["account_code"] == config.KEY_ACCOUNT_CODE, np.median(weight) * 10, weight)
    accounts["activity_weight"] = weight

    is_trading_partner = classes.isin(["supplier", "dealer"]).to_numpy()
    partners = int(is_trading_partner.sum())
    series = _series_codes(2 * partners, rng)
    accounts["invoice_series"] = None
    accounts["waybill_series"] = None
    accounts["series_offset"] = 1
    accounts.loc[is_trading_partner, "invoice_series"] = series[:partners]
    accounts.loc[is_trading_partner, "waybill_series"] = series[partners:]
    accounts.loc[is_trading_partner, "series_offset"] = rng.integers(1_000, 90_000, partners)
    return accounts.sort_values("account_code").reset_index(drop=True)


def real_customers(accounts: pd.DataFrame) -> pd.DataFrame:
    """Returns identifiable end customers: 120- and A... accounts, without collectors or internals."""
    return accounts[accounts["account_class"].isin(REAL_CUSTOMER_CLASSES)]


def assign_sources(products: pd.DataFrame, accounts: pd.DataFrame, roles: pd.DataFrame,
                   rng: np.random.Generator) -> pd.DataFrame:
    """Gives every product one primary supplier and some products one dealer source.

    Args:
        products: Product master.
        accounts: Chart of accounts.
        roles: Product roles.
        rng: Random generator.

    Returns:
        Products with ``supplier_code`` and ``dealer_code`` columns.
    """
    products = products.copy()
    suppliers = accounts[accounts["account_class"] == "supplier"]
    products["supplier_code"] = None
    for brand, index in products.groupby("brand").groups.items():
        brand_suppliers = suppliers.loc[suppliers["brand"] == brand, "account_code"].to_numpy()
        products.loc[index, "supplier_code"] = rng.choice(brand_suppliers, len(index))

    role = products["product_code"].map(roles.set_index("product_code")["role"])
    buyers = products.index[~role.isin(config.NO_REGULAR_PURCHASE_ROLES)].to_numpy()
    chosen = rng.choice(buyers, int(round(len(buyers) * config.DEALER_SOURCED_SHARE)), replace=False)
    dealers = accounts.loc[accounts["account_class"] == "dealer", "account_code"].to_numpy()
    products["dealer_code"] = None
    products.loc[chosen, "dealer_code"] = rng.permutation(np.resize(rng.permutation(dealers), len(chosen)))
    return products
