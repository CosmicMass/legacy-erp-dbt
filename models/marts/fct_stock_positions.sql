-- Stock positions: one row per product in the master, today.
-- Three figures side by side: the balance view, the depot source and the
-- movement ledger, with the status that says which figure differs (T10,
-- T11, T12). No winner is picked.
-- A separate fact, not columns in dim_products: stock is a measurement, not
-- a description. Snapshots after v1 would add a date here and leave the
-- dimension untouched.

with positions as (

    select * from {{ ref('int_products_stock_reconciled') }}

),

final as (

    select
        product_code,
        stock_status,
        is_in_balance_view,
        is_in_depot_source,
        has_movements,
        balance_view_qty,
        depot_source_qty,
        movement_qty,
        untracked_depot_qty,
        balance_view_gap,
        depot_source_gap

    from positions

)

select * from final
