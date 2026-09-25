-- T15: dirty product codes and near-duplicate products.
-- Codes carry double dashes, stray spaces, non-breaking spaces, en dashes
-- and mojibake (T15a). The same size also exists as several products of
-- different brands or materials: a base-code match is not a product match
-- (T15b).
-- Three checks:
--   1. every dirty raw code cleans to the expected code;
--   2. the base codes shared by more than one product are exactly the T15b
--      families (both directions);
--   3. each family has the expected number of members.
-- Returns one row per failure.

with answer_key as (

    select
        case_id,
        entity_key,
        expected_value

    from {{ ref('trap_manifest') }}
    where trap_id = 'T15'

),

products as (

    select * from {{ ref('dim_products') }}

),

families_expected as (

    select entity_key
    from answer_key
    where case_id = 'T15b_near_duplicate_family'

),

families_actual as (

    select distinct base_code as entity_key
    from products
    where base_code_product_count > 1

),

family_sizes as (

    select
        base_code,
        max(base_code_product_count) as member_count

    from products
    group by base_code

)

-- The raw code is the key here, not a cleaned one: cleaning is under test.
select
    'T15a: cleaned code differs' as check_name,
    answer_key.entity_key,
    answer_key.expected_value,
    products.product_code as actual_value

from answer_key
left join products
    on answer_key.entity_key = products.product_code_raw
where answer_key.case_id = 'T15a_dirty_code'
    and products.product_code is distinct from answer_key.expected_value

union all

{{ set_mismatches('T15b: near-duplicate families', 'families_expected', 'families_actual') }}

union all

select
    'T15b: family size differs' as check_name,
    answer_key.entity_key,
    answer_key.expected_value,
    cast(family_sizes.member_count as varchar) as actual_value

from answer_key
left join family_sizes
    on answer_key.entity_key = family_sizes.base_code
where answer_key.case_id = 'T15b_near_duplicate_family'
    and family_sizes.member_count is distinct from cast(answer_key.expected_value as bigint)
