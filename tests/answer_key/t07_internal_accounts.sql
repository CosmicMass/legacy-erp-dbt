-- T7: internal counter-accounts hide inside the customer prefix.
-- Their outbound rows are identical to real open sales; only the account
-- tells them apart. The structural signal (a small 120- segment) finds them,
-- but also flags two real customers, so a human review decides.
-- Three checks:
--   1. the internal accounts are exactly the T7a accounts (both directions);
--   2. each internal account has the expected number of adjustment lines;
--   3. the structural candidates are exactly T7a + T7b (both directions).
-- Returns one row per failure.

with answer_key as (

    select
        case_id,
        entity_key,
        expected_value

    from {{ ref('trap_manifest') }}
    where trap_id = 'T7'

),

accounts as (

    select * from {{ ref('dim_accounts') }}

),

internal_expected as (

    select entity_key from answer_key where case_id = 'T7a_internal_account'

),

internal_actual as (

    select account_code as entity_key from accounts where account_class = 'internal'

),

candidates_expected as (

    select entity_key from answer_key

),

candidates_actual as (

    select account_code as entity_key from accounts where is_internal_candidate

),

internal_lines as (

    select
        account_code,
        count(*) as line_count

    from {{ ref('int_stock_movements_classified') }}
    where flow = 'internal_adjustment'
    group by account_code

)

{{ set_mismatches('T7a: internal accounts', 'internal_expected', 'internal_actual') }}

union all

select
    'T7a: internal line count differs' as check_name,
    answer_key.entity_key,
    answer_key.expected_value,
    cast(coalesce(internal_lines.line_count, 0) as varchar) as actual_value

from answer_key
left join internal_lines
    on answer_key.entity_key = internal_lines.account_code
where answer_key.case_id = 'T7a_internal_account'
    and cast(answer_key.expected_value as bigint) <> coalesce(internal_lines.line_count, 0)

union all

{{ set_mismatches('T7: structural candidates', 'candidates_expected', 'candidates_actual') }}
