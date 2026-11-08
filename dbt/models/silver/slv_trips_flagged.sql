{#
  Silver (audit): every bronze row, with one boolean column per data-quality rule.

  Rows are FLAGGED here, not dropped, so that:
    * the exclusion logic lives in exactly one place,
    * every excluded row is explainable ("why isn't my trip in the dashboard?"),
    * the dashboard's Data Quality view can report on rule hit-rates.
  `slv_trips` then keeps only rows where is_valid = true.
#}
with trips as (
    select * from {{ ref('brz_yellow_trips') }}
),

zones as (
    select location_id from {{ ref('slv_zones') }}
),

deduped as (
    select
        trips.*,
        -- TLC occasionally publishes the same trip twice (identical meter record).
        -- Keep the first occurrence by file position; flag the rest.
        row_number() over (
            partition by vendor_id, pickup_at, dropoff_at, pickup_location_id,
                         dropoff_location_id, fare_amount, total_amount
            order by source_file, source_row_number
        ) > 1 as dq_duplicate
    from trips
),

flagged as (
    select
        d.*,
        datediff('second', pickup_at, dropoff_at) / 60.0          as trip_duration_minutes,

        (pickup_at is null or dropoff_at is null)                  as dq_missing_timestamp,
        -- each monthly file contains a few stray trips from other months/years
        coalesce(date_trunc('month', pickup_at)::date != source_month, true)
                                                                   as dq_outside_source_month,
        coalesce(dropoff_at <= pickup_at, false)                   as dq_non_positive_duration,
        coalesce(datediff('minute', pickup_at, dropoff_at)
                 > {{ var('max_trip_hours') }} * 60, false)       as dq_excessive_duration,
        coalesce(trip_distance_miles <= 0, true)                   as dq_zero_distance,
        coalesce(trip_distance_miles > {{ var('max_trip_miles') }}, false)
                                                                   as dq_excessive_distance,
        -- negative amounts are voids / chargebacks / adjustments, not trips
        coalesce(fare_amount < 0 or total_amount < 0, true)        as dq_negative_amount,
        coalesce(fare_amount > {{ var('max_fare_amount') }}, false) as dq_excessive_fare,
        -- distance and duration can each look fine while together being impossible
        -- (e.g. 5 miles in 10 seconds): meter/GPS glitches
        coalesce(trip_distance_miles
                 / nullif(datediff('second', pickup_at, dropoff_at) / 3600.0, 0)
                 > {{ var('max_avg_speed_mph') }}, false)          as dq_implausible_speed,
        (pz.location_id is null or dz.location_id is null)         as dq_unknown_zone
    from deduped d
    left join zones pz on d.pickup_location_id = pz.location_id
    left join zones dz on d.dropoff_location_id = dz.location_id
)

select
    *,
    not ({{ dq_rules() | join(' or ') }}) as is_valid
from flagged
