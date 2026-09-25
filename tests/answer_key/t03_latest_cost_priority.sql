-- T3: the latest cost needs a priority, not just a date.
-- Ranking by date alone lets a return win (T3a), misses the opening-row
-- fallback (T3b), invents a cost from returns (T3c), or lets an opening row
-- beat a purchase on the same date (T3d).
-- Checks the latest cost of every T3 product. An empty expected value
-- means the cost must be NULL. Returns one row per product that differs.

with expected as (

    select
        case_id,
        entity_key,
        {{ clean_product_code('entity_key') }} as product_code,
        cast(nullif(expected_value, '') as decimal(18, 8)) as expected_cost

    from {{ ref('trap_manifest') }}
    where trap_id = 'T3'

),

products as (

    select * from {{ ref('dim_products') }}

)

select
    expected.case_id || ': latest cost differs' as check_name,
    expected.entity_key,
    cast(expected.expected_cost as varchar) as expected_value,
    cast(products.latest_cost as varchar) as actual_value

from expected
left join products
    on expected.product_code = products.product_code
where products.product_code is null
    or products.latest_cost is distinct from expected.expected_cost
