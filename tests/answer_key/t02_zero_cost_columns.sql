-- T2: there is no usable cost column.
-- The two cost-named columns are 0 on every row; the real cost is the unit
-- price on a purchase row. Staging drops them.
-- Checks the T2 metrics: every raw row reached staging, and no raw row has
-- a non-zero cost column. Returns one row per metric that differs.

with expected as (

    select
        entity_key as metric,
        cast(expected_value as bigint) as expected_value

    from {{ ref('trap_manifest') }}
    where case_id = 'T2_zero_cost_columns'

),

raw_movements as (

    select * from {{ ref('raw_tblsthar') }}

),

actual as (

    select 'movement_rows' as metric, count(*) as actual_value
    from {{ ref('stg_erp__stock_movements') }}
    union all
    select 'rows_with_nonzero_cost_columns', count(*)
    from raw_movements
    where cast(STHAR_MALIYET as decimal(18, 8)) <> 0
        or cast(STHAR_ORT_MALIYET as decimal(18, 8)) <> 0

)

select
    'T2 metric differs' as check_name,
    coalesce(expected.metric, actual.metric) as entity_key,
    cast(expected.expected_value as varchar) as expected_value,
    cast(actual.actual_value as varchar) as actual_value

from expected
full outer join actual
    on expected.metric = actual.metric
where expected.expected_value is distinct from actual.actual_value
