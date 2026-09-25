-- Stock movements, renamed and typed. One row per document line.
-- Movement type and document type keep their ERP codes: what a combination
-- of codes means (sale, purchase, open sale...) is decided in intermediate.
-- The two cost-named columns are dropped: they are 0 on every row (T2), and
-- a test on the seed proves it.

with source as (

    select * from {{ ref('raw_tblsthar') }}

),

renamed as (

    select
        -- Numeric, so it sorts correctly: as text, '10' < '9' (T4).
        cast(INCKEYNO as bigint) as insert_key,
        {{ clean_product_code('STOK_KODU') }} as product_code,
        STOK_KODU as product_code_raw,
        cast(STHAR_TARIH as date) as movement_date,
        FISNO as document_number,
        STHAR_HTUR as movement_type,
        case STHAR_GCKOD
            when 'G' then 'inbound'
            when 'C' then 'outbound'
        end as direction,
        STHAR_FTIRSIP as document_type,
        cast(STHAR_GCMIK as decimal(18, 4)) as quantity,
        -- Full stored precision, never DOUBLE (T14, T16).
        cast(STHAR_DOVFIAT as decimal(18, 8)) as unit_price,
        {{ decode_currency('STHAR_DOVTIP', 'stock_movements') }} as currency,
        STHAR_CARIKOD as account_code,
        DEPO_KODU as depot_code,
        cast(STHAR_KDV as integer) as vat_rate_percent

    from source

),

final as (

    select
        *,
        -- Inbound adds stock, outbound removes it: stock is a plain sum().
        case direction
            when 'inbound' then quantity
            when 'outbound' then -quantity
        end as signed_quantity

    from renamed

)

select * from final
