{# Silver: cleaned TLC taxi zone dimension, built from the official lookup seed. #}
select
    locationid::number                                   as location_id,
    nullif(trim(borough), '')                            as borough,
    nullif(trim(zone), '')                               as zone_name,
    nullif(trim(service_zone), '')                       as service_zone,
    zone in ('JFK Airport', 'LaGuardia Airport', 'Newark Airport')
                                                         as is_airport,
    -- 264 / 265 are TLC placeholders ("Unknown" / "Outside of NYC"), not real zones
    locationid::number not in (264, 265)                 as is_known_zone
from {{ ref('taxi_zone_lookup') }}
