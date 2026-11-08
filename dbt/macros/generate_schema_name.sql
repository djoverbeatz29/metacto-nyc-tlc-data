{#
  Use the layer name (bronze / silver / gold / reference) as the schema verbatim,
  instead of dbt's default "<target_schema>_<custom_schema>". Layer schemas are then
  stable, readable names the dashboard and analysts can rely on.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
