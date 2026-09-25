-- Chart of accounts with a business class. One row per account.
-- The prefix gives the default class (T6). Two kinds of account cannot be
-- told apart by the data alone: internal counter-accounts (T7) and
-- collectors (T8). They take their class from the human review.

with accounts as (

    select * from {{ ref('stg_erp__accounts') }}

),

reviews as (

    select * from {{ ref('stg_reference__account_reviews') }}

),

with_segment_size as (

    select
        *,
        -- Legacy codes (A..., S...) have no segment, so no size.
        case
            when account_segment is not null
                then count(*) over (partition by account_prefix, account_segment)
        end as segment_size

    from accounts

),

classified as (

    select
        with_segment_size.account_code,
        with_segment_size.account_name,
        with_segment_size.account_prefix,
        with_segment_size.account_segment,
        with_segment_size.segment_size,

        -- T7 structural signal: internal counter-accounts sit alone, or
        -- nearly alone, in their own 120- segment. It also flags real
        -- customers in small segments: a detector, not a classifier.
        with_segment_size.account_prefix = '120'
            and with_segment_size.segment_size <= {{ var('internal_account_max_segment_size') }}
            as is_internal_candidate,

        reviews.account_code is not null as is_reviewed,
        reviews.review_note,

        -- A review wins over the prefix. A new prefix becomes NULL, and the
        -- not_null test fails loudly.
        case
            when reviews.reviewed_class is not null then reviews.reviewed_class
            when with_segment_size.account_prefix in ('120', 'A') then 'end_customer'
            when with_segment_size.account_prefix in ('320', 'S') then 'trade_partner'
        end as account_class

    from with_segment_size
    left join reviews
        on with_segment_size.account_code = reviews.account_code

)

select * from classified
