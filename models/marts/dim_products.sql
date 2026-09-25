-- Products: one row per product in the master, with everything that
-- describes a product in one place: identity (T15), currency (T13) and the
-- latest cost (T2-T5).
-- Marts select, join and name things. Every rule lives in intermediate.

with products as (

    select * from {{ ref('stg_erp__products') }}

),

currencies as (

    select * from {{ ref('int_products_currency_checked') }}

),

costs as (

    select * from {{ ref('int_products_latest_cost') }}

),

final as (

    select
        products.product_code,
        products.product_code_raw,
        products.product_name,
        products.product_group_code,
        products.category_code,
        products.brand,

        -- T15: how many products share this size. For similarity analysis
        -- only: a base-code match is not a product match.
        products.base_code,
        count(*) over (
            partition by products.product_group_code, products.base_code
        ) as base_code_product_count,

        -- Prices are in sale_currency: the currency the movements prove, not
        -- necessarily the one the master claims (T13).
        products.list_price,
        products.dealer_price,
        currencies.sale_currency,
        currencies.claimed_currency,
        currencies.sale_currency_source,
        currencies.is_currency_flag_wrong,

        -- T2-T4: the latest cost, in its own currency. NULL when the product
        -- has no purchase and no opening row.
        costs.latest_cost,
        costs.cost_currency,
        costs.cost_source,
        costs.cost_date,

        -- T5: a reference figure only, never a cost.
        costs.latest_adjustment_price,
        costs.adjustment_currency,
        costs.adjustment_date

    from products
    left join currencies
        on products.product_code = currencies.product_code
    left join costs
        on products.product_code = costs.product_code

)

select * from final
