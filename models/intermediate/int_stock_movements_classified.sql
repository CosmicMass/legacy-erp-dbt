-- Stock movements with their business meaning. One row per document line.
-- This is the only model that reads the raw code combinations. Every later
-- model uses flow, so each rule lives in one place.
--
-- The codes decide the flow. The account decides only where the codes are
-- ambiguous: H + outbound (open sale or internal adjustment, T7) and L
-- (customer, dealer or purchase return, T9). Document type is never used to
-- find T7 rows: real customers also use type 3.

with movements as (

    select * from {{ ref('stg_erp__stock_movements') }}

),

accounts as (

    select
        account_code,
        account_class

    from {{ ref('int_accounts_classified') }}

),

joined as (

    select
        movements.*,
        accounts.account_class

    from movements
    left join accounts
        on movements.account_code = accounts.account_code

),

classified as (

    select
        *,
        -- An unknown combination becomes NULL, and the not_null test fails loudly.
        case
            when movement_type = 'A' and direction = 'inbound' then 'opening'
            when movement_type = 'J' and direction = 'inbound' and document_type = '2' then 'purchase'
            when movement_type = 'J' and direction = 'outbound' and document_type = '1' then 'sale_invoice'
            -- T7: identical to an open sale, byte for byte. Only the account differs.
            when movement_type = 'H' and direction = 'outbound'
                and account_class = 'internal' then 'internal_adjustment'
            -- T1: a real sale that is never invoiced.
            when movement_type = 'H' and direction = 'outbound'
                and account_class in ('end_customer', 'collector', 'trade_partner') then 'open_sale'
            -- T5: carries a price, but it is a reference figure, never a cost.
            when movement_type = 'H' and direction = 'inbound'
                and document_type = '4' then 'customer_adjustment'
            -- T9: on trade partner accounts, returns go both ways.
            when movement_type = 'L' and direction = 'inbound'
                and account_class in ('end_customer', 'collector') then 'customer_return'
            when movement_type = 'L' and direction = 'inbound'
                and account_class = 'trade_partner' then 'dealer_return'
            when movement_type = 'L' and direction = 'outbound'
                and account_class = 'trade_partner' then 'purchase_return'
            when movement_type = 'N' and direction = 'inbound' then 'purchase_waybill'
            when movement_type = 'B' and direction = 'inbound' then 'transfer_in'
            when movement_type = 'B' and direction = 'outbound' then 'transfer_out'
        end as flow

    from joined

),

final as (

    select
        *,
        -- T1: sales are invoiced sales plus open sales.
        flow in ('sale_invoice', 'open_sale') as is_sale,

        -- T9: a customer or dealer return reverses a sale. A purchase return
        -- sends goods back to a supplier: that is purchasing, not sales.
        flow in ('customer_return', 'dealer_return') as is_sale_return,

        -- Who bought, on sales and sale returns. Dealer sales are real sales,
        -- but not end-customer sales (T6).
        case
            when flow in ('sale_invoice', 'open_sale', 'customer_return', 'dealer_return') then
                case account_class
                    when 'end_customer' then 'end_customer'
                    when 'collector' then 'collector'
                    when 'trade_partner' then 'dealer'
                end
        end as sales_channel,

        -- VAT-exclusive, in the document currency, at full precision (T14, T16).
        -- Widen first: DuckDB types DECIMAL(18,4) x DECIMAL(18,8) as
        -- DECIMAL(18,12), which overflows at 1,000,000.
        cast(quantity as decimal(38, 4)) * unit_price as line_amount

    from classified

)

select * from final
