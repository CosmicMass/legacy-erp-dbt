-- T1 invariant: an open sale is never invoiced, so H and J rows never share
-- a document number. If they ever do, the ERP has started to convert open
-- sales into invoices, and counting both would count the revenue twice.
-- Returns one row per document number that carries both H and J rows.

select
    document_number,
    count(distinct movement_type) as movement_types

from {{ ref('int_stock_movements_classified') }}
where movement_type in ('H', 'J')
group by document_number
having count(distinct movement_type) > 1
