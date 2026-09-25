-- Account ledger, renamed and typed. One row per sale invoice.
-- The amount is VAT-inclusive and rounded to the cent (T14). The currency is
-- decoded with the ledger's own mapping (T13).

with source as (

    select * from {{ ref('raw_tblcahar') }}

),

renamed as (

    select
        CARI_KOD as account_code,
        FISNO as document_number,
        cast(TARIH as date) as invoice_date,
        cast(DOV_TUTAR as decimal(18, 2)) as amount_incl_vat,
        {{ decode_currency('DOVTIP', 'account_ledger') }} as currency

    from source

)

select * from renamed
