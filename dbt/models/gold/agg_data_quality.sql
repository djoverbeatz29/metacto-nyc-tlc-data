{#
  Gold mart — Data Quality (the candidate-choice feature).
  Grain: one row per source month x data-quality rule.
  A row can break several rules, so rule counts overlap; `rows_excluded_only_by_rule`
  shows how many rows each rule is solely responsible for removing.
#}
{%- set rules = dq_rules() -%}

with flagged as (
    select
        *,
        {% for r in rules %}{{ r }}::int{{ ' + ' if not loop.last }}{% endfor %} as rules_failed
    from {{ ref('slv_trips_flagged') }}
),

totals as (
    select
        source_month,
        count(*)            as total_rows,
        count_if(is_valid)  as valid_rows,
        sum(total_amount)   as total_amount_all_rows,
        sum(iff(is_valid, total_amount, 0)) as total_amount_valid_rows
    from flagged
    group by 1
),

by_rule as (
    {% for r in rules %}
    select
        source_month,
        '{{ r | replace("dq_", "") }}'                as rule_name,
        count_if({{ r }})                            as rows_flagged,
        count_if({{ r }} and rules_failed = 1)       as rows_excluded_only_by_rule,
        sum(iff({{ r }}, total_amount, 0))           as total_amount_flagged
    from flagged
    group by 1
    {{ 'union all' if not loop.last }}
    {% endfor %}
)

select
    r.source_month,
    r.rule_name,
    r.rows_flagged,
    r.rows_excluded_only_by_rule,
    r.total_amount_flagged,
    t.total_rows,
    t.valid_rows,
    t.total_rows - t.valid_rows                     as excluded_rows,
    round(r.rows_flagged / nullif(t.total_rows, 0), 6) as pct_rows_flagged,
    t.total_amount_all_rows,
    t.total_amount_valid_rows
from by_rule r
join totals t using (source_month)
