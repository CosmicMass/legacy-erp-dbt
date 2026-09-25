{#
    Compares two sets of keys in both directions, for the answer-key tests.
    Recall: every expected key is found. Precision: nothing else is found.
    Returns one row per key that is in only one of the two sets.

    Both arguments name a CTE (or relation) with one column: entity_key.
    The output has the columns of every answer-key test: check_name,
    entity_key, expected_value and actual_value.

    Usage, inside a test:
      {{ set_mismatches('internal accounts', 'internal_expected', 'internal_actual') }}
#}
{% macro set_mismatches(check_name, expected, actual) -%}
    select
        '{{ check_name }}' as check_name,
        coalesce(expected.entity_key, actual.entity_key) as entity_key,
        case when expected.entity_key is null then 'not in set' else 'in set' end as expected_value,
        case when actual.entity_key is null then 'not in set' else 'in set' end as actual_value

    from {{ expected }} as expected
    full outer join {{ actual }} as actual
        on expected.entity_key = actual.entity_key
    where expected.entity_key is null
        or actual.entity_key is null
{%- endmacro %}
