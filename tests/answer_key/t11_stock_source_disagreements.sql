-- T11: neither stock source is authoritative on quantity.
-- The balance view and the depot source mostly agree, but disagree in
-- three ways: (a) the depot total is negative while the balance is higher,
-- (b) the depot shows stock the balance does not, (c) other cases. (d) is a
-- control group where both agree on a negative figure.
-- Four checks:
--   1. the products with a disagreement are exactly T11a + T11b + T11c
--      (both directions);
--   2. case a is found as depot_source_differs, case b as balance_view_differs;
--   3. the control group d agrees;
--   4. both source figures match the answer key ("balance=X;depot_total=Y").
-- Returns one row per failure.

with answer_key as (

    select
        case_id,
        entity_key,
        {{ clean_product_code('entity_key') }} as product_code,
        expected_value,
        cast(regexp_extract(expected_value, 'balance=(-?[0-9.]+)', 1) as decimal(38, 4)) as expected_balance,
        cast(regexp_extract(expected_value, 'depot_total=(-?[0-9.]+)', 1) as decimal(38, 4)) as expected_depot_total

    from {{ ref('trap_manifest') }}
    where trap_id = 'T11'

),

positions as (

    select * from {{ ref('fct_stock_positions') }}

),

disagreements_expected as (

    select product_code as entity_key
    from answer_key
    where case_id in ('T11a_depot_negative', 'T11b_depot_higher', 'T11c_other_mismatch')

),

disagreements_actual as (

    select product_code as entity_key
    from positions
    where stock_status in (
        'balance_view_differs', 'depot_source_differs', 'both_differ', 'missing_from_depot_source'
    )

),

joined as (

    select
        answer_key.*,
        positions.stock_status,
        positions.balance_view_qty,
        positions.depot_source_qty,
        case answer_key.case_id
            when 'T11a_depot_negative' then 'depot_source_differs'
            when 'T11b_depot_higher' then 'balance_view_differs'
            when 'T11d_both_negative' then 'agree'
        end as expected_status

    from answer_key
    left join positions
        on answer_key.product_code = positions.product_code

)

{{ set_mismatches('T11: products with a stock disagreement', 'disagreements_expected', 'disagreements_actual') }}

union all

select
    case_id || ': status differs' as check_name,
    entity_key,
    expected_status as expected_value,
    stock_status as actual_value

from joined
where expected_status is not null
    and stock_status is distinct from expected_status

union all

select
    case_id || ': source figures differ' as check_name,
    entity_key,
    expected_value,
    'balance=' || coalesce(cast(balance_view_qty as varchar), 'NULL')
        || ';depot_total=' || coalesce(cast(depot_source_qty as varchar), 'NULL') as actual_value

from joined
where balance_view_qty is distinct from expected_balance
    or depot_source_qty is distinct from expected_depot_total
