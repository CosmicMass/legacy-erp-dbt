-- T10: the balance view is missing products.
-- Some products that hold stock have no row in the balance view at all.
-- COALESCE(balance, 0) would hide them as "zero stock". Absent and zero
-- are different findings.
-- Three checks:
--   1. the products missing from the balance view are exactly T10a
--      (both directions);
--   2. their movement stock equals the true stock in the answer key;
--   3. the T10b control products are present with a balance of 0, not NULL.
-- Returns one row per failure.

with answer_key as (

    select
        case_id,
        entity_key,
        {{ clean_product_code('entity_key') }} as product_code,
        expected_value

    from {{ ref('trap_manifest') }}
    where trap_id = 'T10'

),

positions as (

    select * from {{ ref('fct_stock_positions') }}

),

missing_expected as (

    select product_code as entity_key
    from answer_key
    where case_id = 'T10a_missing_from_balance'

),

missing_actual as (

    select product_code as entity_key
    from positions
    where stock_status = 'missing_from_balance_view'

),

joined as (

    select
        answer_key.*,
        positions.product_code is not null as is_in_model,
        positions.is_in_balance_view,
        positions.balance_view_qty,
        positions.movement_qty

    from answer_key
    left join positions
        on answer_key.product_code = positions.product_code

)

{{ set_mismatches('T10a: products missing from the balance view', 'missing_expected', 'missing_actual') }}

union all

select
    'T10a: true stock differs' as check_name,
    entity_key,
    expected_value,
    cast(movement_qty as varchar) as actual_value

from joined
where case_id = 'T10a_missing_from_balance'
    and (not is_in_model or movement_qty is distinct from cast(expected_value as decimal(38, 4)))

union all

select
    'T10b: zero balance is not present as 0' as check_name,
    entity_key,
    expected_value,
    coalesce(cast(balance_view_qty as varchar), 'absent') as actual_value

from joined
where case_id = 'T10b_zero_balance_control'
    and not (
        coalesce(is_in_balance_view, false)
        and balance_view_qty = cast(expected_value as decimal(38, 4))
    )
