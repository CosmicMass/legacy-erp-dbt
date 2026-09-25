-- Sale invoices: one row per sale invoice.
-- The invoice total recomputed from its lines, next to the account ledger
-- (T14), and the total a person gets from the 2-decimal prices on screen
-- (T16). The table a finance user checks.

with invoices as (

    select * from {{ ref('int_sale_invoices_reconciled') }}

),

final as (

    select
        document_number,
        account_code,
        invoice_date,
        currency,
        vat_rate_percent,
        line_count,
        net_amount,
        computed_amount_incl_vat,
        ledger_amount_incl_vat,
        is_in_ledger,
        amount_difference,
        display_amount_incl_vat,
        display_difference,
        has_display_gap

    from invoices

)

select * from final
