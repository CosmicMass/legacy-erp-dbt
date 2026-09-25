-- T6: account prefixes and the customer filter.
-- Sales split three ways: identifiable end customers, collectors and
-- dealers. Internal counter-accounts post rows that look like sales but
-- are not. Some dealers are bidirectional: we buy from them and sell to them.
-- Checks the nine T6 metrics: sale lines and quantity per class, and the
-- number of bidirectional partners. Returns one row per metric that differs.

with expected as (

    select
        entity_key as metric,
        cast(expected_value as decimal(38, 4)) as expected_value

    from {{ ref('trap_manifest') }}
    where case_id = 'T6_sales_by_account_class'

),

sales as (

    select * from {{ ref('fct_sales') }}
    where not is_sale_return

),

internal_rows as (

    select * from {{ ref('int_stock_movements_classified') }}
    where flow = 'internal_adjustment'

),

by_channel as (

    select
        sales_channel,
        count(*) as sale_lines,
        sum(sales_quantity) as sale_quantity

    from sales
    group by sales_channel

),

actual as (

    select 'sale_lines_' || sales_channel as metric, cast(sale_lines as decimal(38, 4)) as actual_value
    from by_channel
    union all
    select 'sale_quantity_' || sales_channel, cast(sale_quantity as decimal(38, 4))
    from by_channel
    union all
    select 'sale_lines_internal', cast(count(*) as decimal(38, 4))
    from internal_rows
    union all
    select 'sale_quantity_internal', cast(sum(quantity) as decimal(38, 4))
    from internal_rows
    union all
    select 'bidirectional_dealers', cast(count(*) as decimal(38, 4))
    from {{ ref('dim_accounts') }}
    where is_bidirectional_partner

)

select
    'T6 metric differs' as check_name,
    coalesce(expected.metric, actual.metric) as entity_key,
    cast(expected.expected_value as varchar) as expected_value,
    cast(actual.actual_value as varchar) as actual_value

from expected
full outer join actual
    on expected.metric = actual.metric
where expected.expected_value is distinct from actual.actual_value
