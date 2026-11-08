{# Gold dimension: taxi zones, with a display label for the dashboard. #}
select
    location_id,
    zone_name,
    borough,
    service_zone,
    is_airport,
    is_known_zone,
    zone_name || ' (' || borough || ')'  as zone_label
from {{ ref('slv_zones') }}
