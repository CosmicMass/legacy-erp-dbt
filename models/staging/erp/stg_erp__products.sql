-- Product master, renamed and typed. One row per product.
-- The product code is cleaned into the join key (T15); the raw code stays for
-- lineage. sale_currency is what the master claims (T13): staging decodes it
-- with the master's own mapping and never corrects it.

with source as (

    select * from {{ ref('raw_tblstsabit') }}

),

renamed as (

    select
        {{ clean_product_code('STOK_KODU') }} as product_code,
        STOK_KODU as product_code_raw,
        STOK_ADI as product_name,
        GRUP_KODU as product_group_code,
        KOD_1 as category_code,
        MARKA as brand,
        cast(SATIS_FIAT1 as decimal(18, 4)) as list_price,
        cast(SATIS_FIAT2 as decimal(18, 4)) as dealer_price,
        {{ decode_currency('SATIS_DOV_TIP', 'product_master') }} as sale_currency

    from source

)

select * from renamed
