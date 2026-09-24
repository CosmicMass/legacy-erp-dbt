"""Self-checks: re-read the raw tables and confirm every planted count.

The checks work on the final text tables, the same data dbt will load. They
recompute each trap from the raw columns, independently of how the generator
planted it, and compare the result with the design and the manifest. If any
check fails, nothing is written.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

import numpy as np
import pandas as pd

from generator import config
from generator.traps.master_data import clean_code

CUSTOMER_PREFIXES = ("120-", "A")
DEALER_PREFIXES = ("320-", "S")


class GeneratorCheckError(RuntimeError):
    """Raised when the generated data does not match the design."""


@dataclass
class CheckRun:
    """Collects check results so one run reports every failure at once."""

    passed: int = 0
    failures: list[str] = field(default_factory=list)

    def expect(self, name: str, actual: object, expected: object) -> None:
        """Records one check that compares an actual value with an expected value."""
        if actual == expected:
            self.passed += 1
        else:
            self.failures.append(f"{name}: expected {expected!r}, got {actual!r}")


def _units(text: pd.Series) -> pd.Series:
    """Parses fixed 8-decimal text into integer units of 1e-8."""
    return text.str.replace(".", "", regex=False).astype("int64")


def _parse_movements(raw: pd.DataFrame) -> pd.DataFrame:
    """Parses the raw movement table into typed columns."""
    return pd.DataFrame({
        "insert_key": raw["INCKEYNO"].astype("int64"),
        "product_code": raw["STOK_KODU"],
        "movement_date": pd.to_datetime(raw["STHAR_TARIH"]),
        "document_number": raw["FISNO"],
        "movement_type": raw["STHAR_HTUR"],
        "direction": raw["STHAR_GCKOD"],
        "document_type": raw["STHAR_FTIRSIP"],
        "quantity": raw["STHAR_GCMIK"].astype("int64"),
        "price_units": _units(raw["STHAR_DOVFIAT"]),
        "currency_code": raw["STHAR_DOVTIP"],
        "account_code": raw["STHAR_CARIKOD"],
        "depot_code": raw["DEPO_KODU"],
    })


def _case_keys(manifest: pd.DataFrame, case_id: str) -> set[str]:
    """Returns the entity keys of one manifest case."""
    return set(manifest.loc[manifest["case_id"] == case_id, "entity_key"])


def _metric(manifest: pd.DataFrame, key: str) -> str:
    """Returns the expected value of one manifest metric."""
    return manifest.loc[(manifest["entity_type"] == "metric") & (manifest["entity_key"] == key),
                        "expected_value"].iloc[0]


def _first_per_product(frame: pd.DataFrame, order_by: list[str], ascending: list[bool]) -> pd.DataFrame:
    """Keeps the whole first row per product after sorting, indexed by product code."""
    ordered = frame.sort_values(["product_code", *order_by], ascending=[True, *ascending])
    return ordered.drop_duplicates("product_code").set_index("product_code")


def _check_shapes(run: CheckRun, tables: dict[str, pd.DataFrame]) -> None:
    run.expect("product rows", len(tables["raw_tblstsabit"]), sum(
        count for brand in config.BRANDS for count in brand.products_per_group.values()))
    run.expect("movement rows", len(tables["raw_tblsthar"]), sum(config.LINE_TOTALS.values()))
    run.expect("product codes unique", tables["raw_tblstsabit"]["STOK_KODU"].is_unique, True)
    run.expect("account codes unique", tables["raw_tblcasabit"]["CARI_KOD"].is_unique, True)
    run.expect("insert keys unique", tables["raw_tblsthar"]["INCKEYNO"].is_unique, True)


def _check_integrity(run: CheckRun, tables: dict[str, pd.DataFrame], m: pd.DataFrame) -> None:
    products = set(tables["raw_tblstsabit"]["STOK_KODU"])
    accounts = set(tables["raw_tblcasabit"]["CARI_KOD"])
    run.expect("movement products exist in master", set(m["product_code"]) <= products, True)
    run.expect("movement accounts exist in account master", set(m["account_code"].dropna()) <= accounts, True)
    run.expect("balance view products exist in master", set(tables["raw_vw_stok_bakiye"]["STOK_KODU"]) <= products,
               True)
    run.expect("depot source products exist in master", set(tables["raw_vw_depo_bakiye"]["STOK_KODU"]) <= products,
               True)
    per_document = m.groupby("document_number").agg(dates=("movement_date", "nunique"),
                                                    accounts=("account_code", "nunique"))
    run.expect("one date per document", int((per_document["dates"] > 1).sum()), 0)
    run.expect("one account per document", int((per_document["accounts"] > 1).sum()), 0)


def _check_combinations(run: CheckRun, m: pd.DataFrame, internal: set[str]) -> None:
    customer_side = m["account_code"].str.startswith(CUSTOMER_PREFIXES).fillna(False)
    dealer_side = m["account_code"].str.startswith(DEALER_PREFIXES).fillna(False)
    is_internal = m["account_code"].isin(internal)
    combo = m["movement_type"] + m["direction"]
    expected = {
        "A+G opening rows": ((combo == "AG").sum(), config.LINE_TOTALS["opening"]),
        "J+G+2 purchase rows": (((combo == "JG") & (m["document_type"] == "2")).sum(), config.LINE_TOTALS["purchase"]),
        "N+G pending waybill rows": ((combo == "NG").sum(), config.LINE_TOTALS["pending_waybill"]),
        "J+C+1 sale rows": (((combo == "JC") & (m["document_type"] == "1")).sum(), config.LINE_TOTALS["sale_invoice"]),
        "H+C open sale rows": (((combo == "HC") & ~is_internal).sum(), config.LINE_TOTALS["open_sale"]),
        "H+C internal rows": (((combo == "HC") & is_internal).sum(), config.LINE_TOTALS["internal_adjustment"]),
        "H+G+4 rows": (((combo == "HG") & (m["document_type"] == "4")).sum(), config.LINE_TOTALS["customer_adjustment"]),
        "customer L+G rows": (((combo == "LG") & customer_side).sum(), config.LINE_TOTALS["customer_return"]),
        "dealer L+G rows": (((combo == "LG") & dealer_side).sum(), config.LINE_TOTALS["dealer_return_in"]),
        "dealer L+C rows": (((combo == "LC") & dealer_side).sum(), config.LINE_TOTALS["dealer_return_out"]),
        "customer L+C rows": (((combo == "LC") & customer_side).sum(), 0),
        "B transfer rows": ((m["movement_type"] == "B").sum(), config.LINE_TOTALS["transfer"]),
    }
    for name, (actual, target) in expected.items():
        run.expect(name, int(actual), target)


def _check_t01_t02(run: CheckRun, tables: dict[str, pd.DataFrame], m: pd.DataFrame) -> None:
    shared = set(m.loc[m["movement_type"] == "H", "document_number"]) & set(
        m.loc[m["movement_type"] == "J", "document_number"])
    run.expect("T1 document numbers shared by H and J", len(shared), 0)
    raw = tables["raw_tblsthar"]
    nonzero = ((raw["STHAR_MALIYET"] != "0.00000000") | (raw["STHAR_ORT_MALIYET"] != "0.00000000")).sum()
    run.expect("T2 rows with a non-zero cost column", int(nonzero), 0)


def _check_costs(run: CheckRun, m: pd.DataFrame, manifest: pd.DataFrame) -> None:
    is_purchase = (m["movement_type"] == "J") & (m["direction"] == "G") & (m["document_type"] == "2")
    is_opening = (m["movement_type"] == "A") & (m["direction"] == "G")

    # The correct rule: priority, then date, then insert key.
    candidates = m[is_purchase | is_opening].copy()
    candidates["priority"] = np.where(is_purchase[is_purchase | is_opening], 1, 2)
    correct = _first_per_product(candidates, ["priority", "movement_date", "insert_key"], [True, False, False])

    # Naive rule 1: latest inbound row with a price, by date and insert key.
    inbound = m[(m["direction"] == "G") & (m["price_units"] > 0)].copy()
    inbound["kind"] = inbound["movement_type"] + inbound["direction"] + inbound["document_type"]
    naive = _first_per_product(inbound, ["movement_date", "insert_key"], [False, False])
    return_products = set(naive.index[(naive["kind"] == "LG4")
                                      & naive["account_code"].str.startswith(CUSTOMER_PREFIXES)])
    adjustment_products = set(naive.index[naive["kind"] == "HG4"])
    run.expect("T3 products where a naive pick is a customer return", return_products,
               _case_keys(manifest, "T3a_return_after_purchase") | _case_keys(manifest, "T3c_no_cost_source"))
    run.expect("T5 products where a naive pick is H+G+4", adjustment_products,
               _case_keys(manifest, "T5a_adjustment_latest") | _case_keys(manifest, "T5b_adjustment_only"))

    # Naive rule 2: purchase or opening row ranked by date only, without priority.
    by_date = _first_per_product(candidates, ["movement_date", "insert_key"], [False, False])
    wrong = by_date.index[by_date["priority"] != correct.reindex(by_date.index)["priority"]]
    run.expect("T3d products where date-only ranking beats priority", set(wrong),
               _case_keys(manifest, "T3d_priority_over_date"))

    # T4: two purchases on the latest purchase date.
    purchases = m[is_purchase]
    latest_date = purchases.groupby("product_code")["movement_date"].transform("max")
    tie = purchases[purchases["movement_date"] == latest_date]
    tie_counts = tie.groupby("product_code").size()
    run.expect("T4 products with a same-date tie", set(tie_counts.index[tie_counts > 1]),
               _case_keys(manifest, "T4_same_date_tie"))
    ordered = tie[tie["product_code"].isin(tie_counts.index[tie_counts > 1])].sort_values(["product_code",
                                                                                         "insert_key"])
    prices = ordered.groupby("product_code")["price_units"].agg(["first", "last"])
    run.expect("T4 ties where the winner has the higher price", int((prices["last"] > prices["first"]).sum()),
               config.T04_WINNER_HIGHER_PRICE)

    # Every planted cost product: the manifest value equals the correct rule.
    cost_cases = manifest[manifest["case_id"].str.match(r"T[345][a-d]?_") & (manifest["entity_type"] == "product")]
    actual = correct["price_units"].reindex(cost_cases["entity_key"])
    expected = _units(cost_cases["expected_value"].fillna("0.00000000")).to_numpy()
    expected_null = cost_cases["expected_value"].isna().to_numpy()
    mismatches = int(((actual.isna().to_numpy() != expected_null)
                      | (~expected_null & (actual.fillna(0).to_numpy() != expected))).sum())
    run.expect("T3-T5 manifest costs match the correct rule", mismatches, 0)


def _check_accounts(run: CheckRun, tables: dict[str, pd.DataFrame], m: pd.DataFrame, manifest: pd.DataFrame,
                    internal: set[str]) -> None:
    accounts = tables["raw_tblcasabit"]
    codes_120 = accounts.loc[accounts["CARI_KOD"].str.startswith("120-"), "CARI_KOD"]
    segment = codes_120.str.split("-").str[1]
    size = segment.map(segment.value_counts())
    flagged = set(codes_120[size <= config.STRUCTURAL_SEGMENT_MAX_SIZE])
    run.expect("T7 structural candidates = internal + false positives", flagged,
               internal | _case_keys(manifest, "T7b_structural_false_positive"))
    internal_rows = m[m["account_code"].isin(internal)]
    run.expect("T7 internal rows are H+C with document type 3 or 4",
               bool(((internal_rows["movement_type"] + internal_rows["direction"]) == "HC").all()
                    and internal_rows["document_type"].isin(["3", "4"]).all()), True)
    run.expect("T7 real open sales also use document type 3", bool(
        ((m["movement_type"] == "H") & (m["direction"] == "C") & ~m["account_code"].isin(internal)
         & (m["document_type"] == "3")).any()), True)

    collectors = _case_keys(manifest, "T8_collector_account")
    sales = m[((m["movement_type"] == "J") & (m["direction"] == "C") & (m["document_type"] == "1"))
              | ((m["movement_type"] == "H") & (m["direction"] == "C") & ~m["account_code"].isin(internal))]
    run.expect("T8 collector sale lines", int(sales["account_code"].isin(collectors).sum()),
               config.SALE_INVOICE_LINES["collector"] + config.OPEN_SALE_LINES["collector"])

    dealer_side = m["account_code"].str.startswith(DEALER_PREFIXES).fillna(False)
    buys = set(m.loc[dealer_side & (m["movement_type"] == "J") & (m["direction"] == "G"), "account_code"])
    sells = set(m.loc[dealer_side & (m["movement_type"] == "J") & (m["direction"] == "C"), "account_code"])
    run.expect("T6 bidirectional dealers", len(buys & sells), config.DEALERS_UNDER_320 + config.DEALERS_UNDER_S)
    run.expect("T6 manifest bidirectional dealers", _metric(manifest, "bidirectional_dealers"),
               str(config.DEALERS_UNDER_320 + config.DEALERS_UNDER_S))


def _check_stock(run: CheckRun, tables: dict[str, pd.DataFrame], m: pd.DataFrame, manifest: pd.DataFrame) -> None:
    signed = np.where(m["direction"] == "G", m["quantity"], -m["quantity"])
    truth = pd.Series(signed).groupby(m["product_code"].to_numpy()).sum()
    by_depot = pd.Series(signed).groupby([m["product_code"].to_numpy(), m["depot_code"].to_numpy()]).sum()
    balance = tables["raw_vw_stok_bakiye"].set_index("STOK_KODU")["BAKIYE"].astype("int64")
    depots = tables["raw_vw_depo_bakiye"].set_index("STOK_KODU")[["DEPO1_BAKIYE", "DEPO2_BAKIYE"]].astype("int64")
    depot_total = depots.sum(axis=1)

    absent = truth.index.difference(balance.index)
    run.expect("T10 products with stock but absent from the balance view",
               set(absent[truth.reindex(absent) != 0]), _case_keys(manifest, "T10a_missing_from_balance"))
    run.expect("T10 products present with a zero balance", set(balance.index[balance == 0]),
               _case_keys(manifest, "T10b_zero_balance_control"))

    both = balance.index.intersection(depot_total.index)
    disagree = set(both[balance.reindex(both) != depot_total.reindex(both)])
    t11 = (_case_keys(manifest, "T11a_depot_negative") | _case_keys(manifest, "T11b_depot_higher")
           | _case_keys(manifest, "T11c_other_mismatch"))
    run.expect("T11 + T12 products where the sources disagree", disagree,
               t11 | _case_keys(manifest, "T12_depot_3_stock"))
    run.expect("T11 agreement rate above 90%", len(disagree) / len(both) < 0.10, True)
    case_a = list(_case_keys(manifest, "T11a_depot_negative"))
    run.expect("T11a depot total negative and balance higher",
               bool(((depot_total[case_a] < 0) & (balance[case_a] > depot_total[case_a])).all()), True)
    case_d = list(_case_keys(manifest, "T11d_both_negative"))
    run.expect("T11d both sources negative and equal",
               bool(((balance[case_d] < 0) & (balance[case_d] == depot_total[case_d])).all()), True)

    undisturbed = both.difference(list(disagree))
    run.expect("movements agree with the balance view outside the traps",
               int((truth.reindex(undisturbed) != balance.reindex(undisturbed)).sum()), 0)

    run.expect("T12 depot codes in movements", sorted(m["depot_code"].unique()), ["1", "2", "3"])
    depot_3 = by_depot.xs("3", level=1)
    run.expect("T12 products with stock in depot 3", set(depot_3.index[depot_3 != 0]),
               _case_keys(manifest, "T12_depot_3_stock"))


def _check_currency(run: CheckRun, tables: dict[str, pd.DataFrame], m: pd.DataFrame, manifest: pd.DataFrame) -> None:
    master_names = {code: name for name, code in config.MASTER_CURRENCY_CODES.items()}
    movement_names = {code: name for name, code in config.MOVEMENT_CURRENCY_CODES.items()}
    master = tables["raw_tblstsabit"].set_index("STOK_KODU")["SATIS_DOV_TIP"].map(master_names)
    traded = m.assign(currency=m["currency_code"].map(movement_names)).groupby("product_code")["currency"]
    run.expect("T13 every product trades in one currency", int((traded.nunique() > 1).sum()), 0)
    traded_currency = traded.first()
    mismatch = set(traded_currency.index[traded_currency != master.reindex(traded_currency.index)])
    # A dormant product has no movements to compare with, even if its flag is wrong.
    planted = _case_keys(manifest, "T13a_brand_flag_mismatch") | _case_keys(manifest, "T13b_magnitude_outlier")
    run.expect("T13 products whose master flag disagrees with movements", mismatch,
               planted & set(traded_currency.index))

    brands = tables["raw_tblstsabit"].set_index("STOK_KODU")["MARKA"]
    compared = pd.DataFrame({"brand": brands.reindex(traded_currency.index), "traded": traded_currency,
                             "flagged": master.reindex(traded_currency.index)})
    brand_mismatch_share = (compared["traded"] != compared["flagged"]).groupby(compared["brand"]).mean()
    run.expect("T13 brands where every moved product disagrees with its flag",
               set(brand_mismatch_share.index[brand_mismatch_share == 1.0]), {config.MISLABELED_BRAND})


def _check_ledger(run: CheckRun, tables: dict[str, pd.DataFrame], m: pd.DataFrame, manifest: pd.DataFrame) -> None:
    raw = tables["raw_tblsthar"]
    invoice_rows = raw[(raw["STHAR_HTUR"] == "J") & (raw["STHAR_GCKOD"] == "C") & (raw["STHAR_FTIRSIP"] == "1")]
    ledger = tables["raw_tblcahar"].set_index("FISNO")
    run.expect("T14 every sale invoice has one ledger row", set(invoice_rows["FISNO"]), set(ledger.index))
    run.expect("T14 ledger document numbers unique", ledger.index.is_unique, True)

    vat = Decimal(1) + Decimal(config.VAT_RATE_PERCENT) / Decimal(100)
    cent = Decimal("0.01")
    exact: dict[str, Decimal] = {}
    display: dict[str, Decimal] = {}
    for document, quantity, price in zip(invoice_rows["FISNO"], invoice_rows["STHAR_GCMIK"],
                                         invoice_rows["STHAR_DOVFIAT"]):
        unit = Decimal(price)
        exact[document] = exact.get(document, Decimal(0)) + Decimal(quantity) * unit
        display[document] = display.get(document, Decimal(0)) + Decimal(quantity) * unit.quantize(
            cent, rounding=ROUND_HALF_UP)
    amounts = {document: Decimal(amount) for document, amount in ledger["DOV_TUTAR"].items()}
    not_reconciling = sum((total * vat).quantize(cent, rounding=ROUND_HALF_UP) != amounts[document]
                          for document, total in exact.items())
    run.expect("T14 invoices not reconciling to the cent", not_reconciling, 0)
    display_gap = {document for document, total in display.items()
                   if (total * vat).quantize(cent, rounding=ROUND_HALF_UP) != amounts[document]}
    run.expect("T16 invoices with a display-precision gap", display_gap,
               _case_keys(manifest, "T16_display_precision_gap"))
    ledger_currency = ledger["DOVTIP"]
    line_currency = invoice_rows.drop_duplicates("FISNO").set_index("FISNO")["STHAR_DOVTIP"]
    run.expect("T14 ledger currency matches invoice currency",
               bool((ledger_currency.reindex(line_currency.index) == line_currency).all()), True)


def _check_product_codes(run: CheckRun, tables: dict[str, pd.DataFrame], manifest: pd.DataFrame) -> None:
    master = tables["raw_tblstsabit"]
    codes = master["STOK_KODU"]
    cleaned = clean_code(codes)
    run.expect("T15 dirty product codes", set(codes[codes != cleaned]), _case_keys(manifest, "T15a_dirty_code"))
    run.expect("T15 cleaned codes stay unique", cleaned.is_unique, True)
    run.expect("T15 dirty code count", int((codes != cleaned).sum()), sum(config.DIRTY_CODES.values()))
    is_seal = master["GRUP_KODU"] == "SEL"
    base = cleaned.str.rsplit("-", n=1).str[0]
    base = base.where(~is_seal, base.str.rsplit("-", n=1).str[0])
    family_size = base.map(base.value_counts())
    families = set(base[family_size > 1])
    run.expect("T15 near-duplicate families", families, _case_keys(manifest, "T15b_near_duplicate_family"))
    run.expect("T15 family count", len(families),
               sum(count for sizes in config.FAMILY_SIZES.values() for count in sizes.values()))


def run_checks(tables: dict[str, pd.DataFrame]) -> CheckRun:
    """Runs every self-check on the raw tables.

    Args:
        tables: Raw seed tables, as they will be written.

    Returns:
        The check run with the number of passed checks.

    Raises:
        GeneratorCheckError: If any check fails. The message lists every failure.
    """
    run = CheckRun()
    manifest = tables["trap_manifest"]
    m = _parse_movements(tables["raw_tblsthar"])
    internal = _case_keys(manifest, "T7a_internal_account")

    _check_shapes(run, tables)
    _check_integrity(run, tables, m)
    _check_combinations(run, m, internal)
    _check_t01_t02(run, tables, m)
    _check_costs(run, m, manifest)
    _check_accounts(run, tables, m, manifest, internal)
    _check_stock(run, tables, m, manifest)
    _check_currency(run, tables, m, manifest)
    _check_ledger(run, tables, m, manifest)
    _check_product_codes(run, tables, manifest)
    if run.failures:
        raise GeneratorCheckError("Self-checks failed:\n  - " + "\n  - ".join(run.failures))
    return run
