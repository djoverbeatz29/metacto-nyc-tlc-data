{#
  Gold mart — Trip Volume Over Time.
  Grain: one row per pickup hour (clock hour, local NYC time).
  The dashboard rolls hours up to day / week; storing additive measures (counts and
  sums, not averages) makes every roll-up exact.
#}
select
    pickup_hour,
    pickup_date,
    pickup_week,
    pickup_hour_of_day,
    pickup_day_of_week,
    pickup_day_name,
    is_weekend,
    count(*)                                as trip_count,
    sum(coalesce(passenger_count, 0))       as passenger_count,
    sum(trip_distance_miles)                as total_distance_miles,
    sum(trip_duration_minutes)              as total_duration_minutes,
    sum(fare_amount)                        as fare_revenue,
    sum(total_amount)                       as total_revenue,
    count_if(is_airport_trip)               as airport_trip_count
from {{ ref('fct_trips') }}
group by all
