-- Chart of accounts, renamed. One row per account.
-- The code's structure is parsed (prefix and middle segment) but not
-- interpreted: deciding who is a real customer is intermediate work (T6, T7).

with source as (

    select * from {{ ref('raw_tblcasabit') }}

),

renamed as (

    select
        CARI_KOD as account_code,
        CARI_ISIM as account_name,

        -- A new prefix becomes NULL, and the not_null test fails loudly.
        case
            when CARI_KOD like '120-%' then '120'
            when CARI_KOD like '320-%' then '320'
            when CARI_KOD like 'A%' then 'A'
            when CARI_KOD like 'S%' then 'S'
        end as account_prefix,

        -- The middle segment of 120-NN-NNN and 320-NN-NNN codes.
        case
            when CARI_KOD like '120-%' or CARI_KOD like '320-%'
                then split_part(CARI_KOD, '-', 2)
        end as account_segment

    from source

)

select * from renamed
