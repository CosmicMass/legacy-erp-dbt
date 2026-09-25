-- Sale currency per product: what the master claims, next to what the
-- movements show (T13). One row per product in the master.
-- The master's flag can be wrong. A whole brand can be flagged EUR while
-- every movement is in USD, and single products can be flagged TL while
-- their prices are FX-sized.
-- The evidence is the brand's traded currency: the one currency that its
-- movements use. Brand level also covers products with no movements of
-- their own. Price size is not used: EUR and USD prices are about the same
-- size, so it could only catch TL errors.

with products as (

    select
        product_code,
        brand,
        sale_currency as claimed_currency

    from {{ ref('stg_erp__products') }}

),

movements as (

    select
        product_code,
        currency

    from {{ ref('int_stock_movements_classified') }}

),

brand_currencies as (

    select
        products.brand,
        count(distinct movements.currency) as brand_currency_count,
        -- Only one currency is evidence. Two or more is no answer, and the
        -- accepted_values test on brand_currency_count fails loudly.
        case
            when count(distinct movements.currency) = 1 then min(movements.currency)
        end as traded_currency

    from movements
    inner join products
        on movements.product_code = products.product_code
    group by products.brand

),

final as (

    select
        products.product_code,
        products.brand,
        products.claimed_currency,
        brand_currencies.traded_currency,
        brand_currencies.brand_currency_count,
        coalesce(
            products.claimed_currency <> brand_currencies.traded_currency,
            false
        ) as is_currency_flag_wrong,

        -- The best evidence: the traded currency when the brand has
        -- movements, otherwise the master's claim.
        coalesce(brand_currencies.traded_currency, products.claimed_currency) as sale_currency,
        case
            when brand_currencies.traded_currency is not null then 'movements'
            else 'master'
        end as sale_currency_source

    from products
    left join brand_currencies
        on products.brand = brand_currencies.brand

)

select * from final
