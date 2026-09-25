-- T16: stored price precision is higher than displayed precision.
-- Prices are stored with up to 8 decimals but shown with 2. A person who
-- recomputes an invoice from the screen gets a different total.
-- Three checks:
--   1. the invoices with a display gap are exactly the T16 invoices (both
--      directions);
--   2. the ledger amount matches the answer key;
--   3. the display-based total matches the one in the answer key note
--      ("Recomputed from 2-decimal display prices: X").
-- Returns one row per failure.

with answer_key as (

    select
        entity_key,
        cast(expected_value as decimal(38, 2)) as expected_ledger_amount,
        cast(regexp_extract(note, 'display prices: (-?[0-9.]+)', 1) as decimal(38, 2)) as expected_display_amount

    from {{ ref('trap_manifest') }}
    where trap_id = 'T16'

),

invoices as (

    select * from {{ ref('fct_sale_invoices') }}

),

gaps_expected as (

    select entity_key from answer_key

),

gaps_actual as (

    select document_number as entity_key from invoices where has_display_gap

),

joined as (

    select
        answer_key.*,
        invoices.ledger_amount_incl_vat,
        invoices.display_amount_incl_vat

    from answer_key
    left join invoices
        on answer_key.entity_key = invoices.document_number

)

{{ set_mismatches('T16: invoices with a display gap', 'gaps_expected', 'gaps_actual') }}

union all

select
    'T16: ledger amount differs' as check_name,
    entity_key,
    cast(expected_ledger_amount as varchar) as expected_value,
    cast(ledger_amount_incl_vat as varchar) as actual_value

from joined
where ledger_amount_incl_vat is distinct from expected_ledger_amount

union all

select
    'T16: display total differs' as check_name,
    entity_key,
    cast(expected_display_amount as varchar) as expected_value,
    cast(display_amount_incl_vat as varchar) as actual_value

from joined
where display_amount_incl_vat is distinct from expected_display_amount
