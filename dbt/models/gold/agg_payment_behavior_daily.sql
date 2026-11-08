{#
  Gold mart — Payment Type Analysis.
  Grain: one row per pickup date x payment type x trip-distance band.
  Distance bands let the dashboard show whether payment mix shifts with trip length.
#}
with trips as (
    select
        *,
        case
            when trip_distance_miles < 1  then '1: < 1 mi'
            when trip_distance_miles < 3  then '2: 1-3 mi'
            when trip_distance_miles < 7  then '3: 3-7 mi'
            when trip_distance_miles < 15 then '4: 7-15 mi'
            else                               '5: 15+ mi'
        end as distance_band
    from {{ ref('fct_trips') }}
)

select
    pickup_date,
    payment_type_id,
    payment_type_name,
    distance_band,
    count(*)                                as trip_count,
    sum(coalesce(passenger_count, 0))       as passenger_count,
    sum(trip_distance_miles)                as total_distance_miles,
    sum(trip_duration_minutes)              as total_duration_minutes,
    sum(fare_amount)                        as fare_revenue,
    sum(tip_amount)                         as tip_revenue,
    sum(total_amount)                       as total_revenue,
    count_if(tip_amount > 0)                as tipped_trip_count,
    count_if(is_airport_trip)               as airport_trip_count
from trips
group by all
