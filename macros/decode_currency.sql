{#
    Decodes a raw currency code into an ISO code (TRY, EUR, USD), using the
    mapping of one source table (T13). Every table has its own mapping in
    var("currency_codes"), because the same code can mean different
    currencies in different tables.

    A code that is not in the mapping becomes NULL. A not_null test on the
    result then fails loudly when the ERP starts using a new code.
#}
{% macro decode_currency(column_name, mapping_name) -%}
    {%- set mappings = var("currency_codes") -%}
    {%- if mapping_name not in mappings -%}
        {{ exceptions.raise_compiler_error("No currency mapping named '" ~ mapping_name ~ "' in var('currency_codes').") }}
    {%- endif -%}
    case {{ column_name }}
        {%- for code, iso_code in mappings[mapping_name].items() %}
        when '{{ code }}' then '{{ iso_code }}'
        {%- endfor %}
    end
{%- endmacro %}
