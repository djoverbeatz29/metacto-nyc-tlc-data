{{ config(cluster_by=['pickup_date']) }}
{#
  Gold fact: one row per valid trip. The single source of truth the aggregate
  marts are built from (and reconcile back to — see tests/).
#}
select
    trip_id,
    pickup_at,
    dropoff_at,
    pickup_date,
    pickup_hour,
    pickup_week,
    pickup_hour_of_day,
    pickup_day_of_week,
    pickup_day_name,
    is_weekend,
    vendor_id,
    payment_type_id,
    payment_type_name,
    rate_code_id,
    rate_code_name,
    pickup_location_id,
    dropoff_location_id,
    is_airport_trip,
    passenger_count,
    trip_distance_miles,
    trip_duration_minutes,
    avg_speed_mph,
    fare_amount,
    tip_amount,
    tolls_amount,
    total_amount,
    total_amount - fare_amount - tip_amount - tolls_amount  as surcharges_and_fees_amount,
    tip_pct_of_fare
from {{ ref('slv_trips') }}
