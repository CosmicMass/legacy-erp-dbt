{#
    Fails for every row where the expression is not true. It replaces
    dbt_utils.expression_is_true, so the project needs no packages.

    NULL counts as a failure: a rule that cannot be evaluated has not passed.

    Usage (model level):
      data_tests:
        - name: invariant_t14_every_invoice_reconciles
          test_name: expression_is_true
          arguments:
            expression: "is_in_ledger and amount_difference = 0"
#}
{% test expression_is_true(model, expression, column_name=None) %}

select *
from {{ model }}
where not coalesce({{ expression }}, false)

{% endtest %}
