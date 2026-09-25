-- Accounts: one row per account, with its class (T6-T8) and its trade
-- roles (T6, T9).
-- The roles are a rollup of the classified movements. They live here, not
-- in int_accounts_classified, because the movement flows depend on the
-- account class: computing them there would create a cycle.

with accounts as (

    select * from {{ ref('int_accounts_classified') }}

),

movements as (

    select * from {{ ref('int_stock_movements_classified') }}

),

activity as (

    select
        account_code,
        bool_or(flow in ('purchase', 'purchase_waybill')) as has_purchases,
        bool_or(is_sale) as has_sales

    from movements
    where account_code is not null
    group by account_code

),

roles as (

    select
        accounts.*,
        coalesce(activity.has_purchases, false) as is_supplier,
        -- A dealer is a trade partner we sell to. Sales to 120- and A...
        -- accounts are customer sales, not dealer sales.
        accounts.account_class = 'trade_partner'
            and coalesce(activity.has_sales, false) as is_dealer

    from accounts
    left join activity
        on accounts.account_code = activity.account_code

),

final as (

    select
        account_code,
        account_name,
        account_prefix,
        account_segment,
        segment_size,
        account_class,
        is_internal_candidate,
        is_reviewed,
        review_note,
        is_supplier,
        is_dealer,
        -- T6: we both buy from and sell to this partner.
        is_supplier and is_dealer as is_bidirectional_partner

    from roles

)

select * from final
