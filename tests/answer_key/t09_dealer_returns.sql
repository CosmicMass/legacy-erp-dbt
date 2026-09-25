-- T9: returns on dealer accounts go both directions.
-- On trade partner accounts, L rows come in (a dealer returns our sale) and
-- go out (we return goods to a supplier) in about the same volume. Customer
-- returns only come in. Customer-return logic applied to every L row would
-- net purchase returns against sales.
-- Checks the four T9 metrics from the classified flows, and that fct_sales
-- holds exactly the customer and dealer returns (no purchase returns).
-- Returns one row per failure.

with expected as (

    select
        entity_key as metric,
        cast(expected_value as bigint) as expected_value

    from {{ ref('trap_manifest') }}
    where case_id = 'T9_dealer_returns'

),

movements as (

    select * from {{ ref('int_stock_movements_classified') }}

),

actual as (

    select 'customer_return_rows_inbound' as metric, count(*) as actual_value
    from movements where flow = 'customer_return'
    union all
    -- Customer returns never go out. Such a row would have no flow at all.
    select 'customer_return_rows_outbound', count(*)
    from movements
    where movement_type = 'L' and direction = 'outbound' and account_class <> 'trade_partner'
    union all
    select 'dealer_return_rows_inbound', count(*)
    from movements where flow = 'dealer_return'
    union all
    select 'dealer_return_rows_outbound', count(*)
    from movements where flow = 'purchase_return'

),

metric_checks as (

    select
        'T9 metric differs' as check_name,
        coalesce(expected.metric, actual.metric) as entity_key,
        cast(expected.expected_value as varchar) as expected_value,
        cast(actual.actual_value as varchar) as actual_value

    from expected
    full outer join actual
        on expected.metric = actual.metric
    where expected.expected_value is distinct from actual.actual_value

),

sales_returns as (

    select count(*) as return_rows
    from {{ ref('fct_sales') }}
    where is_sale_return

),

sales_check as (

    select
        'T9: sale returns in fct_sales differ' as check_name,
        'customer + dealer return rows' as entity_key,
        cast(sum(expected.expected_value) as varchar) as expected_value,
        cast(max(sales_returns.return_rows) as varchar) as actual_value

    from expected
    cross join sales_returns
    where expected.metric in ('customer_return_rows_inbound', 'dealer_return_rows_inbound')
    having sum(expected.expected_value) <> max(sales_returns.return_rows)

)

select * from metric_checks
union all
select * from sales_check
