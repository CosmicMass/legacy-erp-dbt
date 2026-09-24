"""Central configuration for the synthetic legacy-ERP dataset.

Every count from the step 2 design lives here, in one place. The other modules
read these values and never hardcode a count, so the design and the generated
data cannot drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Reproducibility and output
# ---------------------------------------------------------------------------
SEED = 20250101
OUTPUT_DIR = Path("seeds")

# ---------------------------------------------------------------------------
# Calendar: one fiscal year, as a legacy ERP keeps one database per year
# ---------------------------------------------------------------------------
FISCAL_YEAR = 2025
YEAR_START = date(2025, 1, 1)
YEAR_END = date(2025, 12, 31)
# The year-end carry-over is run late in January. Opening rows therefore get
# insert keys that are higher than the first January documents.
OPENING_ENTRY_DATE = date(2025, 1, 27)
# Regular purchases stop here. This leaves room for rows that traps plant
# after the last purchase of a product (T3, T5).
LAST_REGULAR_PURCHASE_DATE = date(2025, 12, 19)
# World returns only go to products whose last purchase is after this date,
# so there is room to date the return before that purchase.
RETURN_ELIGIBLE_AFTER = date(2025, 2, 1)
# The third depot opened in the last quarter (T12).
DEPOT_3_OPENING_DATE = date(2025, 10, 1)
PUBLIC_HOLIDAYS = (
    date(2025, 1, 1),
    date(2025, 3, 31),
    date(2025, 4, 1),
    date(2025, 4, 23),
    date(2025, 5, 1),
    date(2025, 5, 19),
    date(2025, 6, 6),
    date(2025, 6, 9),
    date(2025, 7, 15),
    date(2025, 10, 29),
)
# Share of documents entered after their document date, and the maximum delay.
BACKDATED_SHARE = 0.05
BACKDATED_MAX_DAYS = 21

# ---------------------------------------------------------------------------
# Currencies (T13): every table has its own currency code mapping
# ---------------------------------------------------------------------------
MASTER_CURRENCY_CODES = {"TL": "5", "EUR": "3", "USD": "1"}
MOVEMENT_CURRENCY_CODES = {"TL": "0", "EUR": "1", "USD": "2"}
LEDGER_CURRENCY_CODES = MOVEMENT_CURRENCY_CODES
VAT_RATE_PERCENT = 20
TL_PER_EUR_PRICE_FACTOR = 44.0
TL_MONTHLY_INFLATION = 0.022
# T16: TL prices are almost always typed with 2 decimals.
TL_EXTRA_PRECISION_SHARE = 0.02
TL_EXTRA_PRECISION_DECIMALS = 4
FX_PRICE_DECIMALS = 8


# ---------------------------------------------------------------------------
# Brands and products
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Brand:
    """An invented brand.

    Attributes:
        name: Brand name as stored in the product master.
        abbreviation: Suffix used in product codes.
        currency: The currency the brand is really bought and sold in.
        price_factor: Price level compared with an average brand.
        products_per_group: Number of products per product group.
        suppliers: Number of supplier accounts for this brand.
    """

    name: str
    abbreviation: str
    currency: str
    price_factor: float
    products_per_group: dict[str, int]
    suppliers: int


BRANDS = (
    Brand("VORNELL", "VRN", "EUR", 1.25, {"BRG": 120}, suppliers=4),
    Brand("KADRIX", "KDX", "USD", 1.05, {"BRG": 90}, suppliers=3),
    Brand("ZELTRAK", "ZLT", "USD", 0.95, {"BRG": 40}, suppliers=2),
    Brand("ORLENTA", "ORL", "EUR", 1.00, {"SEL": 110}, suppliers=3),
    Brand("MIRVANO", "MRV", "EUR", 1.00, {"BLT": 70}, suppliers=2),
    Brand("TANDREL", "TDR", "TL", 0.70, {"BRG": 80, "SEL": 60, "BLT": 30}, suppliers=11),
)
PRODUCT_GROUPS = ("BRG", "SEL", "BLT")
CATEGORY_NAMES = {
    "DG": "DEEP GROOVE BALL BEARING",
    "TR": "TAPERED ROLLER BEARING",
    "CY": "CYLINDRICAL ROLLER BEARING",
    "SA": "SELF-ALIGNING BALL BEARING",
    "OS": "OIL SEAL",
    "NV": "NARROW V-BELT",
    "VB": "CLASSIC V-BELT",
}
CATEGORY_BASE_PRICE_EUR = {"DG": 5.0, "TR": 12.0, "CY": 20.0, "SA": 15.0, "OS": 3.0, "NV": 8.0, "VB": 5.0}
SEAL_MATERIALS = ("NBR", "FKM")
SEAL_MATERIAL_WEIGHTS = (0.7, 0.3)
DEALER_PRICE_RATIO = 0.82
COST_RATIO_RANGE = (0.55, 0.68)
MIN_POPULARITY = 0.25

# T15: near-duplicate families. {family size: number of families} per group.
FAMILY_SIZES = {
    "BRG": {4: 8, 3: 12, 2: 20},
    "SEL": {4: 2, 3: 6, 2: 12},
    "BLT": {2: 10},
}

# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------
# Normal 120- customer segments: {segment: number of accounts}.
CUSTOMER_SEGMENTS = {"01": 24, "02": 18, "03": 12, "05": 30, "07": 15, "10": 22, "12": 10, "15": 19}
# A real customer that sits alone in its own segment (T7 false positive).
KEY_ACCOUNT_CODE = "120-20-001"
# A real customer that shares its segment with an internal account (T7).
SHARED_SEGMENT_CUSTOMER_CODE = "120-16-001"
LEGACY_CUSTOMER_COUNT = 30
# T8: collector accounts, keyed by segment ("A" = legacy prefix).
COLLECTOR_ACCOUNTS = {
    "03": "MISC. SALES - MAIN DEPOT",
    "12": "WALK-IN CUSTOMERS",
    "A": "CASH SALES",
}
TL_SUPPLIERS_UNDER_320 = 6
TL_SUPPLIERS_UNDER_S = 5
DEALERS_UNDER_320 = 12
DEALERS_UNDER_S = 3
DEALER_SOURCED_SHARE = 0.30
SUPPLIER_DELIVERY_DAYS = 22
SUPPLIER_DELIVERY_WEEKDAYS = (0, 1, 2, 3)
DEALER_DELIVERY_DAYS = 10
DEALER_DELIVERY_WEEKDAYS = (4,)
DEALER_PURCHASE_MARKUP = 1.05
PURCHASE_PRICE_NOISE = 0.02
OPENING_PRICE_FACTOR = 0.97


@dataclass(frozen=True)
class InternalAccount:
    """An internal counter-account hidden under the 120- customer prefix (T7).

    Attributes:
        code: Account code.
        name: Account name. Some names reveal the purpose, some do not.
        created_year: Year the account was opened.
        lines: Outbound lines posted to it in the fiscal year.
    """

    code: str
    name: str
    created_year: int
    lines: int


INTERNAL_ACCOUNTS = (
    InternalAccount("120-04-001", "STOCK COUNT DIFFERENCES 2021", 2021, 0),
    InternalAccount("120-09-001", "INVENTORY ADJUSTMENT 2022", 2022, 0),
    InternalAccount("120-11-001", "GENERAL ACCOUNT 3", 2023, 120),
    InternalAccount("120-14-001", "DEPOT OPERATIONS", 2024, 150),
    InternalAccount("120-16-002", "STOCK COUNT 2025", 2025, 230),
)
# A segment with this many accounts or fewer is a structural candidate (T7).
STRUCTURAL_SEGMENT_MAX_SIZE = 2

# Discounts are drawn from these values with these weights.
CUSTOMER_DISCOUNTS = ((0.0, 0.30), (0.05, 0.25), (0.10, 0.20), (0.125, 0.15), (0.15, 0.10))
DEALER_DISCOUNTS = ((0.0, 0.40), (0.02, 0.35), (0.05, 0.25))
LINE_DISCOUNTS = ((0.0, 0.70), (0.02, 0.10), (0.03, 0.10), (0.05, 0.10))

# Own document series: 3 letters, then the year, then 9 digits.
OWN_SERIES = {
    "sale_invoice": "SIV",
    "sale_waybill": "SWB",
    "return": "RTN",
    "purchase_return": "PRT",
    "transfer": "TRF",
    "opening": "OPN",
}

# ---------------------------------------------------------------------------
# Product roles: decided before the world is built, never overlapping
# ---------------------------------------------------------------------------
PRODUCT_ROLES = {
    "dormant": 30,
    "new_product": 20,
    "t03a_return_after_purchase": 40,
    "t03b_opening_fallback": 30,
    "t03c_no_cost_source": 5,
    "t03d_priority_over_date": 5,
    "t04_same_date_tie": 25,
    "t05a_adjustment_latest": 20,
    "t05b_adjustment_only": 5,
    "t05_background": 65,
    "t10_missing_from_balance": 15,
    "t10_zero_balance_control": 40,
    "t11a_depot_negative": 10,
    "t11b_depot_higher": 6,
    "t11c_other_mismatch": 5,
    "t11d_both_negative": 5,
    "t12_depot_3_stock": 8,
}
NO_MOVEMENT_ROLES = frozenset({"dormant", "t03c_no_cost_source", "t05b_adjustment_only"})
NO_OPENING_ROLES = NO_MOVEMENT_ROLES | {"new_product"}
NO_REGULAR_PURCHASE_ROLES = NO_MOVEMENT_ROLES | {"t03b_opening_fallback", "t03d_priority_over_date"}
EXACT_STOCK_ROLES = frozenset({"t10_zero_balance_control", "t11d_both_negative"})
NOT_BRANCH_ROLES = NO_MOVEMENT_ROLES | EXACT_STOCK_ROLES | {"t12_depot_3_stock"}
BRANCH_PRODUCTS = 140
TRANSFERS_PER_BRANCH_PRODUCT = 2
BRANCH_OUTBOUND_SHARE = 0.4

# ---------------------------------------------------------------------------
# Movement lines: the totals from the step 2 design table
# ---------------------------------------------------------------------------
LINE_TOTALS = {
    "opening": 540,
    "purchase": 2_400,
    "pending_waybill": 120,
    "sale_invoice": 14_000,
    "open_sale": 3_200,
    "internal_adjustment": 500,
    "customer_adjustment": 150,
    "customer_return": 550,
    "dealer_return_in": 220,
    "dealer_return_out": 200,
    "transfer": 600,
}
SALE_INVOICE_LINES = {"customer": 11_085, "dealer": 1_800, "collector": 1_100}
OPEN_SALE_LINES = {"customer": 2_800, "collector": 400}
# (mean, maximum) lines per document.
LINES_PER_DOCUMENT = {
    "customer": (4.0, 10),
    "dealer": (6.0, 12),
    "collector": (3.0, 6),
    "open_sale": (3.5, 8),
    "internal": (3.0, 6),
}
OPEN_SALE_DOCUMENT_TYPES = {"3": 0.9, "4": 0.1}
INTERNAL_DOCUMENT_TYPES = {"3": 0.6, "4": 0.4}
MEAN_LINE_QUANTITY = {"BRG": 6.0, "SEL": 10.0, "BLT": 4.0}
DEALER_QUANTITY_MULTIPLIER = 3.0
COLLECTOR_MAX_QUANTITY = 4
RETURN_MAX_QUANTITY = 4
ADJUSTMENT_MAX_QUANTITY = 5

# ---------------------------------------------------------------------------
# Trap parameters
# ---------------------------------------------------------------------------
T03A_RETURN_DISCOUNT = (0.0, 0.10)
T03C_RETURNS_PER_PRODUCT = 2
T04_SAME_DOCUMENT_TIES = 10
T04_WINNER_HIGHER_PRICE = 13
T04_PRICE_GAP = (0.03, 0.10)
T05_EXTRA_ROWS_BEFORE_LATEST = 10
T05_ROWS_PER_ADJUSTMENT_ONLY = 2
T05_BACKGROUND_ROWS = 110
T05_PRICE_RATIO = (0.85, 0.97)
T12_TRANSFER_PAIRS = 20
T12_SALE_LINES = 15
MISLABELED_BRAND = "ZELTRAK"
MISLABELED_BRAND_FLAG = "EUR"
MAGNITUDE_OUTLIERS = 3
MAGNITUDE_OUTLIER_BRANDS = ("VORNELL", "ORLENTA")
MAGNITUDE_OUTLIER_FLAG = "TL"
DIRTY_CODES = {
    "double_dash": 12,
    "trailing_space": 7,
    "leading_space": 3,
    "non_breaking_space": 3,
    "en_dash": 3,
    "mojibake": 2,
}

# ---------------------------------------------------------------------------
# Stock targets
# ---------------------------------------------------------------------------
ENDING_STOCK_SHARE = (0.15, 0.50)
OPENING_STOCK_SHARE = (0.10, 0.40)
BOTH_NEGATIVE_RANGE = (1, 10)
BRANCH_BUFFER_RANGE = (0, 3)
DEPOT_3_STOCK_RANGE = (5, 30)
T11A_DEPOT_DEFICIT_RANGE = (2, 20)
T11C_BALANCE_EXCESS_RANGE = (3, 15)
T11C_DEPOT_EXCESS_RANGE = (2, 10)
T11C_NEGATIVE_BALANCE_RANGE = (1, 5)
