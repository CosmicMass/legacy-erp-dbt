{#
    Fails when a combination of columns is not unique. Returns one row per
    duplicated combination. It replaces dbt_utils.unique_combination_of_columns,
    so the project needs no packages.

    Usage:
      data_tests:
        - unique_combination:
            arguments:
              combination: [product_code, depot_code]
#}
{% test unique_combination(model, combination) %}

select
    {{ combination | join(', ') }},
    count(*) as occurrences
from {{ model }}
group by {{ combination | join(', ') }}
having count(*) > 1

{% endtest %}
