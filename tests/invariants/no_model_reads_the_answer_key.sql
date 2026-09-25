{#
    Architecture guard: models must never read the answer key (CLAUDE.md).
    Tests may read it; models may not, or the models would "find" the traps
    by looking up the answers.

    The test reads dbt's own graph. A model fails when it depends on the
    trap_manifest seed, or when its SQL names the manifest at all (which
    also catches a hardcoded table name that bypasses ref()).
    Returns one row per offending model.
#}

{%- set offenders = [] -%}
{%- if execute -%}
    {%- for node in graph.nodes.values() -%}
        {%- if node.resource_type == 'model' and (
                'seed.legacy_erp.trap_manifest' in node.depends_on.nodes
                or 'trap_manifest' in node.raw_code
            ) -%}
            {%- do offenders.append(node.name) -%}
        {%- endif -%}
    {%- endfor -%}
{%- endif -%}

{% if offenders %}
select model_name
from (values
    {%- for name in offenders %}
    ('{{ name }}'){{ "," if not loop.last }}
    {%- endfor %}
) as offenders (model_name)
{% else %}
select cast(null as varchar) as model_name
where false
{% endif %}
