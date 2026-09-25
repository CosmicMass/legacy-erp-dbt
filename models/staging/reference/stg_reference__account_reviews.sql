-- Account reviews, passed through. One row per reviewed account.
-- Hand-maintained reference data, not an ERP export: the analyst's decision
-- on accounts that the data alone cannot classify (T7, T8). The seed already
-- uses clear English names and text types, so nothing is renamed or cast.

with source as (

    select * from {{ ref('account_reviews') }}

),

renamed as (

    select
        account_code,
        reviewed_class,
        review_note

    from source

)

select * from renamed
