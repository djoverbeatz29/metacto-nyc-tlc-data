{#
  Reconciliation: every gold mart must add up to exactly the same trip count and
  revenue as fct_trips. Catches fan-out joins, dropped rows and grain mistakes.
  Returns rows (= failure) for any mart that does not reconcile.
#}
with fct as (
    select count(*) as trips, sum(total_amount) as revenue from {{ ref('fct_trips') }}
),

marts as (
    select 'agg_trip_volume_hourly' as mart, sum(trip_count) as trips, sum(total_revenue) as revenue
    from {{ ref('agg_trip_volume_hourly') }}
    union all
    select 'agg_zone_revenue_daily', sum(trip_count), sum(total_revenue)
    from {{ ref('agg_zone_revenue_daily') }}
    union all
    select 'agg_payment_behavior_daily', sum(trip_count), sum(total_revenue)
    from {{ ref('agg_payment_behavior_daily') }}
)

select m.*, f.trips as fct_trips, f.revenue as fct_revenue
from marts m
cross join fct f
where m.trips != f.trips
   or abs(m.revenue - f.revenue) > 0.01
