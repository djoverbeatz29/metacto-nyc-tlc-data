{#
  Silver: cleaned, conformed, enriched trips. Grain = one valid trip.
  Codes are decoded and zones are attached here, so gold models are pure aggregation.
#}
with valid as (
    select * from {{ ref('slv_trips_flagged') }}
    where is_valid
),

zones as (select * from {{ ref('slv_zones') }}),
payment_types as (select * from {{ ref('payment_types') }}),
rate_codes as (select * from {{ ref('rate_codes') }}),
vendors as (select * from {{ ref('vendors') }})

select
    t.trip_id,
    t.source_month,

    -- time
    t.pickup_at,
    t.dropoff_at,
    t.pickup_at::date                                   as pickup_date,
    date_trunc('hour', t.pickup_at)                     as pickup_hour,
    date_trunc('week', t.pickup_at)::date               as pickup_week,
    hour(t.pickup_at)                                   as pickup_hour_of_day,
    dayofweekiso(t.pickup_at)                           as pickup_day_of_week,  -- 1 = Mon
    dayname(t.pickup_at)                                as pickup_day_name,
    dayofweekiso(t.pickup_at) in (6, 7)                 as is_weekend,

    -- who / how
    t.vendor_id,
    coalesce(v.vendor_name, 'Unknown')                  as vendor_name,
    t.payment_type_id,
    coalesce(p.payment_type_name, 'Unknown')            as payment_type_name,
    t.rate_code_id,
    coalesce(r.rate_code_name, 'Unknown')               as rate_code_name,
    -- 0 or > max is a driver-entry error; keep the trip, null the attribute
    iff(t.passenger_count between 1 and {{ var('max_passenger_count') }},
        t.passenger_count, null)                        as passenger_count,

    -- where
    t.pickup_location_id,
    pz.zone_name                                        as pickup_zone,
    pz.borough                                          as pickup_borough,
    t.dropoff_location_id,
    dz.zone_name                                        as dropoff_zone,
    dz.borough                                          as dropoff_borough,
    (pz.is_airport or dz.is_airport)                    as is_airport_trip,

    -- trip measures
    t.trip_distance_miles,
    round(t.trip_duration_minutes, 2)                   as trip_duration_minutes,
    round(t.trip_distance_miles / nullif(t.trip_duration_minutes / 60, 0), 2)
                                                        as avg_speed_mph,

    -- money
    t.fare_amount,
    t.extra_amount,
    t.mta_tax_amount,
    t.tip_amount,
    t.tolls_amount,
    t.improvement_surcharge_amount,
    t.congestion_surcharge_amount,
    t.airport_fee_amount,
    t.cbd_congestion_fee_amount,
    t.total_amount,
    -- tips are only captured for card payments; cash tip_amount is always ~0
    iff(t.payment_type_id = 1 and t.fare_amount > 0,
        round(t.tip_amount / t.fare_amount, 4), null)   as tip_pct_of_fare

from valid t
left join zones pz          on t.pickup_location_id = pz.location_id
left join zones dz          on t.dropoff_location_id = dz.location_id
left join payment_types p   on t.payment_type_id = p.payment_type_id
left join rate_codes r      on t.rate_code_id = r.rate_code_id
left join vendors v         on t.vendor_id = v.vendor_id
