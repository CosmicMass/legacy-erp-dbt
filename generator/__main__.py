"""Entry point: ``python -m generator``.

Pipeline:
    1. Build the clean world (master data, product roles, movements).
    2. Plant the traps that add or change rows.
    3. Balance stock quantities, number documents, assign insert keys.
    4. Derive the balance sources and the ledger; plant the source traps.
    5. Register the facts every test needs in the trap manifest.
    6. Make product codes dirty (T15) everywhere at once.
    7. Self-check every count on the raw tables; write the CSVs only if all pass.
"""

from __future__ import annotations

import pandas as pd

from generator import catalog, checks, config, keys, ledger, output, roles, stock, world
from generator.common import rng_for
from generator.traps import accounts as account_traps
from generator.traps import cost as cost_traps
from generator.traps import documents as document_traps
from generator.traps import master_data as master_traps
from generator.traps import stock as stock_traps


def build() -> dict[str, pd.DataFrame]:
    """Builds every raw table and the trap manifest.

    Returns:
        Seed name to raw table, every column as text.
    """
    # 1. Clean world.
    products = catalog.build_products(rng_for("products"))
    accounts = catalog.build_accounts(rng_for("accounts"))
    product_roles = roles.assign_roles(products, rng_for("roles"))
    products = catalog.assign_sources(products, accounts, product_roles, rng_for("sources"))
    movements = world.build_world(products, accounts, product_roles)

    # 2. Traps that add or change movement rows.
    accounts, movements = account_traps.plant_t07_internal_accounts(accounts, movements, products, product_roles)
    movements = cost_traps.plant_t03a_return_after_purchase(movements, products, accounts, product_roles,
                                                            rng_for("t03a"))
    movements = cost_traps.plant_t03c_no_cost_source(movements, products, accounts, product_roles, rng_for("t03c"))
    movements = cost_traps.plant_t03d_priority_over_date(movements, products, accounts, product_roles,
                                                         rng_for("t03d"))
    movements = cost_traps.plant_t04_same_date_tie(movements, product_roles, rng_for("t04"))
    movements = cost_traps.plant_t05_customer_adjustments(movements, products, accounts, product_roles,
                                                          rng_for("t05"))
    movements = stock_traps.plant_t12_third_depot(movements, products, accounts, product_roles, rng_for("t12"))

    # 3. Quantities, document numbers, insert keys.
    movements, targets = stock.balance_quantities(movements, product_roles, rng_for("stock"))
    movements = keys.assign_document_numbers(movements, accounts)
    movements = keys.assign_insert_keys(movements, rng_for("insert_keys"))
    movements = cost_traps.finalize_t04_prices(movements, product_roles, rng_for("t04.prices"))

    # 4. Balance sources and ledger.
    balance_view, depot_balance = stock.build_balance_sources(movements)
    balance_view, t10_manifest = stock_traps.plant_t10_missing_from_balance(balance_view, targets, product_roles)
    balance_view, depot_balance, t11_manifest = stock_traps.plant_t11_source_disagreements(
        balance_view, depot_balance, product_roles, rng_for("t11"))
    invoice_ledger = ledger.build_ledger(movements)

    # 5. Master-data trap and registrations.
    products, t13_manifest = master_traps.plant_t13_currency_flags(products, product_roles, rng_for("t13"))
    manifest = pd.concat([
        document_traps.register_t01_open_sales(movements),
        document_traps.register_t02_zero_cost_columns(movements),
        cost_traps.register_cost_expectations(movements, product_roles),
        account_traps.register_t06_sales_by_class(movements, accounts),
        account_traps.register_t07_structural_signal(accounts),
        account_traps.register_t08_collectors(movements, accounts),
        account_traps.register_t09_dealer_returns(movements),
        t10_manifest,
        t11_manifest,
        stock_traps.register_t12_third_depot(movements),
        t13_manifest,
        document_traps.register_t14_ledger(invoice_ledger),
        document_traps.register_t16_display_precision(movements, invoice_ledger),
    ], ignore_index=True)

    # 6. Dirty product codes, applied to every table that holds a product code.
    code_map, t15_manifest = master_traps.plant_t15_dirty_codes(products, rng_for("t15"))
    products = master_traps.apply_code_mapping(products, code_map)
    movements = master_traps.apply_code_mapping(movements, code_map)
    balance_view = master_traps.apply_code_mapping(balance_view, code_map)
    depot_balance = master_traps.apply_code_mapping(depot_balance, code_map)
    is_product = manifest["entity_type"] == "product"
    manifest.loc[is_product, "entity_key"] = manifest.loc[is_product, "entity_key"].map(
        lambda code: code_map.get(code, code))
    manifest = pd.concat([manifest, t15_manifest], ignore_index=True)

    return output.to_raw_tables(products, accounts, movements, balance_view, depot_balance, invoice_ledger,
                                manifest)


def main() -> None:
    """Builds, checks and writes the synthetic dataset."""
    tables = build()
    run = checks.run_checks(tables)
    output.write_tables(tables, config.OUTPUT_DIR)
    print(f"Self-checks passed: {run.passed}")
    for name, table in tables.items():
        print(f"  {config.OUTPUT_DIR / (name + '.csv')}: {len(table):>6} rows")
    cases = tables["trap_manifest"].groupby("case_id", sort=False).size()
    print("Trap manifest rows per case:")
    for case_id, count in cases.items():
        print(f"  {case_id:<34} {count:>5}")


if __name__ == "__main__":
    main()
