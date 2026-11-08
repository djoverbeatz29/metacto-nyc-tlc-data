{#
  Gold mart — Revenue by Pickup Zone.
  Grain: one row per pickup date x pickup zone. Daily (not month-total) so the
  dashboard's date filter applies; additive measures so averages are computed
  correctly after filtering (sum / count, never avg of avgs).
#}
select
    f.pickup_date,
    f.pickup_location_id,
    z.zone_name                             as pickup_zone,
    z.borough                               as pickup_borough,
    z.zone_label                            as pickup_zone_label,
    z.is_airport,
    z.is_known_zone,
    count(*)                                as trip_count,
    sum(f.fare_amount)                      as fare_revenue,
    sum(f.tip_amount)                       as tip_revenue,
    sum(f.total_amount)                     as total_revenue,
    sum(f.trip_distance_miles)              as total_distance_miles
from {{ ref('fct_trips') }} f
join {{ ref('dim_zones') }} z on f.pickup_location_id = z.location_id
group by all
