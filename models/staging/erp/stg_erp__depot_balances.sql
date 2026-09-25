-- Depot balance source, unpivoted. One row per product and depot.
-- The source hardcodes one column per depot. Unpivoting turns the depot into
-- data (depot_code '1' and '2'), so it joins like every other depot code.
-- A third depot has no column in the source at all (T12).

with source as (

    select * from {{ ref('raw_vw_depo_bakiye') }}

),

unpivoted as (

    select STOK_KODU, '1' as depot_code, DEPO1_BAKIYE as stock_qty_text from source
    union all
    select STOK_KODU, '2' as depot_code, DEPO2_BAKIYE as stock_qty_text from source

),

renamed as (

    select
        {{ clean_product_code('STOK_KODU') }} as product_code,
        STOK_KODU as product_code_raw,
        depot_code,
        cast(stock_qty_text as decimal(18, 4)) as stock_qty

    from unpivoted

)

select * from renamed
