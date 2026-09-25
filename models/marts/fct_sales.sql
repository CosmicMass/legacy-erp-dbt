-- Sales: one row per sale line or sale-return line.
-- In: invoiced sales and open sales (T1), customer and dealer returns (T9).
-- Out: internal adjustments (T7) and purchase returns (T9).
-- Measures take the sales point of view: a sale is positive, a return is
-- negative, so sum(sales_amount) is net sales. This sign flip is the only
-- thing this model adds; every rule comes from intermediate.
-- Money is in the document currency. Never sum it across currencies.

with movements as (

    select * from {{ ref('int_stock_movements_classified') }}

),

sales_lines as (

    select * from movements
    where is_sale or is_sale_return

),

final as (

    select
        insert_key,
        document_number,
        movement_date as document_date,
        product_code,
        account_code,
        depot_code,
        flow,
        is_sale_return,
        -- T6, T8: revenue counts every channel; sales to identifiable end
        -- customers count end_customer only.
        sales_channel,
        currency,
        unit_price,
        case when is_sale_return then -quantity else quantity end as sales_quantity,
        case when is_sale_return then -line_amount else line_amount end as sales_amount

    from sales_lines

)

select * from final
