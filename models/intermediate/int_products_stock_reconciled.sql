-- Stock per product from three figures, side by side. One row per product
-- in the master.
--   balance_view_qty: the balance view. Some products are missing (T10).
--   depot_source_qty: the depot source. It only has depots 1 and 2 (T12).
--   movement_qty:     the sum of signed movement quantities. Movements start
--                     with the opening rows, so this is the ledger's own view.
-- Neither source is authoritative (T11). The model says which figure
-- differs from the movements, and never picks a winner.

with products as (

    select product_code from {{ ref('stg_erp__products') }}

),

balances as (

    select * from {{ ref('stg_erp__stock_balances') }}

),

depot_balances as (

    select * from {{ ref('stg_erp__depot_balances') }}

),

movements as (

    select * from {{ ref('int_stock_movements_classified') }}

),

-- The depots the depot source knows, read from the data, not hardcoded.
source_depots as (

    select distinct depot_code from depot_balances

),

depot_totals as (

    select
        product_code,
        sum(stock_qty) as depot_source_qty

    from depot_balances
    group by product_code

),

movement_totals as (

    select
        movements.product_code,
        sum(movements.signed_quantity) as movement_qty,
        -- T12: stock in depots that the depot source has no column for.
        sum(
            case when source_depots.depot_code is null then movements.signed_quantity else 0 end
        ) as untracked_depot_qty

    from movements
    left join source_depots
        on movements.depot_code = source_depots.depot_code
    group by movements.product_code

),

joined as (

    -- No COALESCE on the balance sources: absent and zero are different
    -- findings (T10). Movements are different: no rows means nothing ever
    -- moved, so the ledger's stock is a real zero.
    select
        products.product_code,
        balances.product_code is not null as is_in_balance_view,
        depot_totals.product_code is not null as is_in_depot_source,
        movement_totals.product_code is not null as has_movements,
        balances.stock_qty as balance_view_qty,
        depot_totals.depot_source_qty,
        coalesce(movement_totals.movement_qty, 0) as movement_qty,
        coalesce(movement_totals.untracked_depot_qty, 0) as untracked_depot_qty

    from products
    left join balances
        on products.product_code = balances.product_code
    left join depot_totals
        on products.product_code = depot_totals.product_code
    left join movement_totals
        on products.product_code = movement_totals.product_code

),

compared as (

    select
        *,
        -- Positive: the source shows more than the movements.
        balance_view_qty - movement_qty as balance_view_gap,
        -- The depot source is compared only with the depots it knows.
        depot_source_qty - (movement_qty - untracked_depot_qty) as depot_source_gap

    from joined

),

final as (

    select
        *,
        case
            when not is_in_balance_view and not is_in_depot_source and not has_movements
                then 'no_stock_record'
            when not is_in_balance_view then 'missing_from_balance_view'
            when not is_in_depot_source then 'missing_from_depot_source'
            when balance_view_gap = 0 and depot_source_gap = 0 then 'agree'
            when depot_source_gap = 0 then 'balance_view_differs'
            when balance_view_gap = 0 then 'depot_source_differs'
            else 'both_differ'
        end as stock_status

    from compared

)

select * from final
