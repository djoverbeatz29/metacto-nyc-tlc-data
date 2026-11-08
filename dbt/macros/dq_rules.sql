{#
  Single registry of silver data-quality rule columns. Used by slv_trips_flagged
  (to compute is_valid) and agg_data_quality (to report on each rule), so adding a
  rule means: add its dq_* column in slv_trips_flagged + add its name here.
#}
{% macro dq_rules() -%}
    {{ return([
        'dq_duplicate',
        'dq_missing_timestamp',
        'dq_outside_source_month',
        'dq_non_positive_duration',
        'dq_excessive_duration',
        'dq_zero_distance',
        'dq_excessive_distance',
        'dq_negative_amount',
        'dq_excessive_fare',
        'dq_implausible_speed',
        'dq_unknown_zone',
    ]) }}
{%- endmacro %}
