{#
  Nothing is silently lost between layers: valid rows in the audit table must equal
  rows in slv_trips, and slv_trips must equal fct_trips.
#}
with counts as (
    select
        (select count_if(is_valid) from {{ ref('slv_trips_flagged') }}) as flagged_valid,
        (select count(*) from {{ ref('slv_trips') }})                  as silver_trips,
        (select count(*) from {{ ref('fct_trips') }})                  as gold_trips
)

select *
from counts
where flagged_valid != silver_trips
   or silver_trips != gold_trips
