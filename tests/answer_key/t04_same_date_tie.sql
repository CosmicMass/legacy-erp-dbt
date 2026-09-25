-- T4: same-date ties make "latest" nondeterministic.
-- Some products have two purchases on their latest purchase date at
-- different prices. The insert key breaks the tie: the row entered last
-- wins. For some products the winner has the higher price, for others the
-- lower, so neither MAX nor MIN passes this test.
-- Returns one row per T4 product whose latest cost differs.

with expected as (

    select
        case_id,
        entity_key,
        {{ clean_product_code('entity_key') }} as product_code,
        cast(nullif(expected_value, '') as decimal(18, 8)) as expected_cost

    from {{ ref('trap_manifest') }}
    where trap_id = 'T4'

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
