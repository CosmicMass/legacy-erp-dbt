-- T1: open sales are real sales and are never invoiced.
-- An open sale (H + outbound) stays a waybill forever. A model that counts
-- only invoices (J) silently loses real revenue.
-- Checks the five T1 metrics of the answer key against fct_sales and the
-- classified movements. Returns one row per metric that differs.

with expected as (

    select
        entity_key as metric,
        cast(expected_value as bigint) as expected_value

    from {{ ref('trap_manifest') }}
    where case_id = 'T1_open_sales'

),

sales as (

    select * from {{ ref('fct_sales') }}

),

shared_documents as (

    select document_number
    from {{ ref('int_stock_movements_classified') }}
    where movement_type in ('H', 'J')
    group by document_number
    having count(distinct movement_type) > 1

),

actual as (

    select 'open_sale_lines' as metric, count(*) as actual_value
    from sales where flow = 'open_sale'
    union all
    select 'open_sale_documents', count(distinct document_number)
    from sales where flow = 'open_sale'
    union all
    select 'sale_invoice_lines', count(*)
    from sales where flow = 'sale_invoice'
    union all
    select 'sale_invoice_documents', count(distinct document_number)
    from sales where flow = 'sale_invoice'
    union all
    select 'documents_shared_by_h_and_j', count(*)
    from shared_documents

)

select
    'T1 metric differs' as check_name,
    coalesce(expected.metric, actual.metric) as entity_key,
    cast(expected.expected_value as varchar) as expected_value,
    cast(actual.actual_value as varchar) as actual_value

from expected
full outer join actual
    on expected.metric = actual.metric
where expected.expected_value is distinct from actual.actual_value
