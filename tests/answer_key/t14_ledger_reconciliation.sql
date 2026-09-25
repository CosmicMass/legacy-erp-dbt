-- T14: prices are per unit, VAT-exclusive and net of discount.
-- So round(sum(quantity x unit price) x (1 + VAT rate), 2) equals the
-- account receivable in the ledger, to the cent.
-- Checks the two T14 metrics: how many invoices are in the ledger, and how
-- many do not reconcile. Returns one row per metric that differs.

with expected as (

    select
        entity_key as metric,
        cast(expected_value as bigint) as expected_value

    from {{ ref('trap_manifest') }}
    where case_id = 'T14_ledger_reconciliation'

),

invoices as (

    select * from {{ ref('fct_sale_invoices') }}

),

actual as (

    select 'sale_invoices_in_ledger' as metric, count(*) as actual_value
    from invoices where is_in_ledger
    union all
    select 'invoices_not_reconciling', count(*)
    from invoices where not coalesce(is_in_ledger and amount_difference = 0, false)

)

select
    'T14 metric differs' as check_name,
    coalesce(expected.metric, actual.metric) as entity_key,
    cast(expected.expected_value as varchar) as expected_value,
    cast(actual.actual_value as varchar) as actual_value

from expected
full outer join actual
    on expected.metric = actual.metric
where expected.expected_value is distinct from actual.actual_value
