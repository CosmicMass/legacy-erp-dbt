-- Product master, renamed and typed. One row per product.
-- The product code is cleaned into the join key (T15); the raw code stays for
-- lineage. sale_currency is what the master claims (T13): staging decodes it
-- with the master's own mapping and never corrects it.
-- base_code is the code's structure parsed, not interpreted (T15). A code is
-- <base code>[-<seal material>]-<brand suffix>, so the base code is the code
-- without its last segment, and for seals without the last two.

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

),

parsed as (

    select
        *,
        -- Same size, different brand or material: 6001-ZZ-KDX and
        -- 6001-ZZ-VRN share 6001-ZZ. The variant (ZZ, 2RS, C3) is part of
        -- the size, so 6003-ZZ-KDX and 6003-2RS-VRN do not share a base code.
        -- For similarity analysis only, never a join key.
        case
            when product_group_code = 'SEL' then regexp_replace(product_code, '-[^-]+-[^-]+$', '')
            else regexp_replace(product_code, '-[^-]+$', '')
        end as base_code

    from renamed

)

select * from parsed
