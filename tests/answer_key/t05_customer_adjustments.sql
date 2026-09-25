-- T5: an undocumented inbound combination that looks like a cost.
-- H + inbound + 4 rows carry a price a little below cost. They are a
-- reference figure, never a cost: where one is the latest inbound row
-- (T5a) the cost is still the purchase, and where only they exist (T5b)
-- the cost is NULL.
-- Two checks per T5 product: the latest cost matches the answer key, and
-- the adjustment price is kept in its own column. Returns one row per failure.

with expected as (

    select
        case_id,
        entity_key,
        {{ clean_product_code('entity_key') }} as product_code,
        cast(nullif(expected_value, '') as decimal(18, 8)) as expected_cost

    from {{ ref('trap_manifest') }}
    where trap_id = 'T5'

),

products as (

    select * from {{ ref('dim_products') }}

),

joined as (

    select
        expected.*,
        products.product_code is not null as is_in_model,
        products.latest_cost,
        products.latest_adjustment_price

    from expected
    left join products
        on expected.product_code = products.product_code

)

select
    case_id || ': latest cost differs' as check_name,
    entity_key,
    cast(expected_cost as varchar) as expected_value,
    cast(latest_cost as varchar) as actual_value

from joined
where not is_in_model
    or latest_cost is distinct from expected_cost

union all

select
    case_id || ': adjustment price missing' as check_name,
    entity_key,
    'a price' as expected_value,
    cast(latest_adjustment_price as varchar) as actual_value

from joined
where latest_adjustment_price is null
