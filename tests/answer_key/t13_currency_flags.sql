-- T13: the currency code can lie.
-- One brand is flagged EUR on every master row, but every movement is in
-- USD (T13a). A few single products are flagged TL while their prices are
-- FX-sized (T13b). The movements are the evidence.
-- Two checks:
--   1. the products with a wrong flag are exactly T13a + T13b (both
--      directions);
--   2. each one resolves to the true currency.
-- Returns one row per failure.

with answer_key as (

    select
        case_id,
        entity_key,
        {{ clean_product_code('entity_key') }} as product_code,
        -- The generator writes TL; staging decodes it to the ISO code TRY.
        case expected_value when 'TL' then 'TRY' else expected_value end as expected_currency

    from {{ ref('trap_manifest') }}
    where trap_id = 'T13'

),

products as (

    select * from {{ ref('dim_products') }}

),

flagged_expected as (

    select product_code as entity_key from answer_key

),

flagged_actual as (

    select product_code as entity_key from products where is_currency_flag_wrong

)

{{ set_mismatches('T13: products with a wrong currency flag', 'flagged_expected', 'flagged_actual') }}

union all

select
    answer_key.case_id || ': sale currency differs' as check_name,
    answer_key.entity_key,
    answer_key.expected_currency as expected_value,
    products.sale_currency as actual_value

from answer_key
left join products
    on answer_key.product_code = products.product_code
where products.sale_currency is distinct from answer_key.expected_currency
