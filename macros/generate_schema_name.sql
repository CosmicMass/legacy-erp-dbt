{#
    Use a custom schema name as-is: "staging", "marts", "answer_key".

    dbt's default prefixes it with the target schema ("main_staging"). That
    prefix keeps developers apart on a shared warehouse. Here every developer
    has their own local DuckDB file, so clean names are safe.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
