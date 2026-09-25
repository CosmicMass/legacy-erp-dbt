-- T8: collector accounts are real sales; do not exclude them.
-- Some customer accounts gather anonymous walk-in buyers. Their sales are
-- real revenue, flagged because there is no identifiable end customer.
-- Two checks:
--   1. the collector accounts are exactly the T8 accounts (both directions);
--   2. each collector keeps all its sale lines in fct_sales.
-- Returns one row per failure.

with answer_key as (

    select
        entity_key,
        expected_value

    from {{ ref('trap_manifest') }}
    where case_id = 'T8_collector_account'

),

collectors_expected as (

    select entity_key from answer_key

),

collectors_actual as (

    select account_code as entity_key
    from {{ ref('dim_accounts') }}
    where account_class = 'collector'

),

sale_lines as (

    select
        account_code,
        count(*) as line_count

    from {{ ref('fct_sales') }}
    where not is_sale_return
    group by account_code

)

{{ set_mismatches('T8: collector accounts', 'collectors_expected', 'collectors_actual') }}

union all

select
    'T8: sale line count differs' as check_name,
    answer_key.entity_key,
    answer_key.expected_value,
    cast(coalesce(sale_lines.line_count, 0) as varchar) as actual_value

from answer_key
left join sale_lines
    on answer_key.entity_key = sale_lines.account_code
where cast(answer_key.expected_value as bigint) <> coalesce(sale_lines.line_count, 0)
