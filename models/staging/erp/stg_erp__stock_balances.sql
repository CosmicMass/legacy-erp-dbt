-- Balance view, renamed and typed. One row per product that the view knows.
-- Passed through unchanged: no COALESCE, no filling. A product that is absent
-- here stays absent, so intermediate can tell "absent" from "zero" (T10).

with source as (

    select * from {{ ref('raw_vw_stok_bakiye') }}

),

renamed as (

    select
        {{ clean_product_code('STOK_KODU') }} as product_code,
        STOK_KODU as product_code_raw,
        cast(BAKIYE as decimal(18, 4)) as stock_qty

    from source

)

select * from renamed
