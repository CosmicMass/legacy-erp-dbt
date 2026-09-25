-- T12: a third depot the depot source does not know about.
-- The depot source hardcodes columns for depots 1 and 2, but movements also
-- carry depot 3. Its stock is missing from the depot source, so a naive
-- comparison reports a false disagreement for every depot 3 product.
-- Four checks:
--   1. the depot codes in movements match the answer key;
--   2. the products with stock outside the known depots are exactly T12
--      (both directions);
--   3. that untracked stock equals the depot 3 stock in the answer key;
--   4. once depot 3 is counted, those products agree.
-- Returns one row per failure.

with answer_key as (

    select
        case_id,
        entity_key,
        {{ clean_product_code('entity_key') }} as product_code,
        expected_value

    from {{ ref('trap_manifest') }}
    where trap_id = 'T12'

),

positions as (

    select * from {{ ref('fct_stock_positions') }}

),

depot_codes as (

    select string_agg(depot_code, ',' order by depot_code) as depot_codes
    from (
        select distinct depot_code
        from {{ ref('int_stock_movements_classified') }}
    ) as distinct_depots

),

untracked_expected as (

    select product_code as entity_key
    from answer_key
    where case_id = 'T12_depot_3_stock'

),

untracked_actual as (

    select product_code as entity_key
    from positions
    where untracked_depot_qty <> 0

),

joined as (

    select
        answer_key.*,
        positions.product_code is not null as is_in_model,
        positions.untracked_depot_qty,
        positions.stock_status

    from answer_key
    left join positions
        on answer_key.product_code = positions.product_code
    where answer_key.case_id = 'T12_depot_3_stock'

)

select
    'T12: depot codes in movements differ' as check_name,
    answer_key.entity_key,
    answer_key.expected_value,
    depot_codes.depot_codes as actual_value

from answer_key
cross join depot_codes
where answer_key.case_id = 'T12_depot_codes'
    and answer_key.expected_value is distinct from depot_codes.depot_codes

union all

{{ set_mismatches('T12: products with stock in an untracked depot', 'untracked_expected', 'untracked_actual') }}

union all

select
    'T12: untracked depot stock differs' as check_name,
    entity_key,
    expected_value,
    cast(untracked_depot_qty as varchar) as actual_value

from joined
where not is_in_model
    or untracked_depot_qty is distinct from cast(expected_value as decimal(38, 4))

union all

select
    'T12: status differs once depot 3 is counted' as check_name,
    entity_key,
    'agree' as expected_value,
    stock_status as actual_value

from joined
where stock_status is distinct from 'agree'
