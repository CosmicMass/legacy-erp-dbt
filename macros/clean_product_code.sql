{#
    Cleans a raw ERP product code into the join key (T15).

    The order matters: characters first, then whitespace, then structure.
      1. Mojibake "Ã—" -> "x". A multiplication sign (U+00D7) was read with the
         wrong code page: its UTF-8 bytes C3 97 show as U+00C3 + U+2014.
      2. En dash (U+2013) -> "-".
      3. Non-breaking space (U+00A0) -> normal space. DuckDB's trim() strips
         it at the edges, but SQL Server and Postgres do not, and trim() never
         touches the middle of a string. Replacing it makes the intent explicit.
      4. trim().
      5. Runs of dashes -> one dash.

    The unique test on stg_erp__products.product_code proves that cleaning
    never merges two different products.
#}
{% macro clean_product_code(column_name) -%}
    regexp_replace(
        trim(
            replace(
                replace(
                    replace({{ column_name }}, chr(195) || chr(8212), 'x'),
                    chr(8211), '-'
                ),
                chr(160), ' '
            )
        ),
        '-{2,}', '-', 'g'
    )
{%- endmacro %}
