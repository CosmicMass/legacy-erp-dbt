-- Sale invoices recomputed from their lines, next to the account ledger.
-- One row per sale invoice.
-- T14: unit prices are per unit, VAT-exclusive and net of discount, so
--   round(sum(quantity x unit price) x (1 + VAT rate), 2)
-- equals the ledger amount to the cent.
-- T16: prices are stored with up to 8 decimals but shown with 2. The same
-- total recomputed from the displayed prices can differ by a few cents.
--
-- No "/" anywhere: in DuckDB every division returns DOUBLE, even between
-- decimals. The VAT factor is built by multiplication, so money stays DECIMAL.

with invoice_lines as (

    select * from {{ ref('int_stock_movements_classified') }}
    where flow = 'sale_invoice'

),

ledger as (

    select * from {{ ref('stg_erp__account_ledger') }}

),

invoices as (

    -- The header columns are grouped, not aggregated. If an invoice's lines
    -- disagree on account, date, currency or VAT rate, the invoice gets two
    -- rows, and the unique test on document_number fails loudly.
    select
        document_number,
        account_code,
        movement_date as invoice_date,
        currency,
        vat_rate_percent,
        count(*) as line_count,
        sum(line_amount) as net_amount,
        sum(cast(quantity as decimal(38, 4)) * round(unit_price, 2)) as display_net_amount

    from invoice_lines
    group by
        document_number,
        account_code,
        movement_date,
        currency,
        vat_rate_percent

),

with_vat as (

    select
        *,
        1 + cast(vat_rate_percent as decimal(5, 2)) * 0.01 as vat_factor

    from invoices

),

amounts as (

    select
        *,
        -- T14: what the invoice must be.
        round(net_amount * vat_factor, 2) as computed_amount_incl_vat,
        -- T16: what a person gets from the 2-decimal prices on screen.
        round(display_net_amount * vat_factor, 2) as display_amount_incl_vat

    from with_vat

),

final as (

    select
        amounts.document_number,
        amounts.account_code,
        amounts.invoice_date,
        amounts.currency,
        amounts.vat_rate_percent,
        amounts.line_count,
        amounts.net_amount,

        -- T14: the recomputed invoice next to the ledger.
        amounts.computed_amount_incl_vat,
        ledger.amount_incl_vat as ledger_amount_incl_vat,
        ledger.document_number is not null as is_in_ledger,
        ledger.amount_incl_vat - amounts.computed_amount_incl_vat as amount_difference,

        -- T16: the display-based total next to the real one.
        amounts.display_amount_incl_vat,
        amounts.display_amount_incl_vat - amounts.computed_amount_incl_vat as display_difference,
        amounts.display_amount_incl_vat <> amounts.computed_amount_incl_vat as has_display_gap

    from amounts
    left join ledger
        on amounts.document_number = ledger.document_number

)

select * from final
