-- Latest cost per product. One row per product in the master.
-- The movement table has no usable cost column (T2): the cost is the unit
-- price on a purchase row. Candidates are ranked by priority first, then
-- date, then insert key:
--   priority 1: purchase (J + inbound + 2)
--   priority 2: opening balance (A + inbound)
-- Priority comes first, so a purchase beats an opening row even on the same
-- date (T3d). Returns are never candidates (T3a). The insert key breaks
-- same-date ties, so the result is the same on every run (T4).
-- Customer adjustments (T5) carry a price too. They are a separate reference
-- tier in their own columns, never a cost.

with products as (

    select product_code from {{ ref('stg_erp__products') }}

),

movements as (

    select * from {{ ref('int_stock_movements_classified') }}

),

cost_candidates as (

    select
        product_code,
        flow,
        unit_price,
        currency,
        movement_date,
        insert_key,
        row_number() over (
            partition by product_code
            order by
                case flow when 'purchase' then 1 when 'opening' then 2 end,
                movement_date desc,
                insert_key desc
        ) as cost_rank

    from movements
    where flow in ('purchase', 'opening')

),

adjustments as (

    select
        product_code,
        unit_price,
        currency,
        movement_date,
        row_number() over (
            partition by product_code
            order by movement_date desc, insert_key desc
        ) as adjustment_rank

    from movements
    where flow = 'customer_adjustment'

),

final as (

    -- Anchored on the master: a product with no cost source keeps its row,
    -- with a NULL cost (T3c, T5b).
    select
        products.product_code,
        cost_candidates.unit_price as latest_cost,
        cost_candidates.currency as cost_currency,
        cost_candidates.flow as cost_source,
        cost_candidates.movement_date as cost_date,
        cost_candidates.insert_key as cost_insert_key,
        adjustments.unit_price as latest_adjustment_price,
        adjustments.currency as adjustment_currency,
        adjustments.movement_date as adjustment_date

    from products
    left join cost_candidates
        on products.product_code = cost_candidates.product_code
        and cost_candidates.cost_rank = 1
    left join adjustments
        on products.product_code = adjustments.product_code
        and adjustments.adjustment_rank = 1

)

select * from final
