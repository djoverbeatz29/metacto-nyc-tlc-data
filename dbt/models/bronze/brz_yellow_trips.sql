{#
  Bronze: a 1:1 view over the landing table.
  Only renames to snake_case, makes types explicit and adds lineage columns.
  No rows are filtered and no values are changed, so bronze always reconciles to raw.
#}
with source as (
    select * from {{ source('raw', 'yellow_tripdata') }}
)

select
    -- lineage: (source file, row number) uniquely identifies a published record
    {{ dbt_utils.generate_surrogate_key(['_source_file', '_source_row_number']) }} as trip_id,
    _source_file                                    as source_file,
    _source_row_number                              as source_row_number,
    to_date(regexp_substr(_source_file, '[0-9]{4}-[0-9]{2}') || '-01')
                                                    as source_month,
    _loaded_at                                      as loaded_at,

    -- identifiers / codes
    vendorid::number                                as vendor_id,
    ratecodeid::number                              as rate_code_id,
    payment_type::number                            as payment_type_id,
    pulocationid::number                            as pickup_location_id,
    dolocationid::number                            as dropoff_location_id,
    store_and_fwd_flag::varchar                     as store_and_fwd_flag,
    request_source::varchar                         as request_source,

    -- timestamps (TLC publishes local NYC wall-clock time, no zone)
    tpep_pickup_datetime::timestamp_ntz             as pickup_at,
    tpep_dropoff_datetime::timestamp_ntz            as dropoff_at,

    -- measures
    passenger_count::number                         as passenger_count,
    trip_distance::number(10, 2)                    as trip_distance_miles,
    fare_amount::number(10, 2)                      as fare_amount,
    extra::number(10, 2)                            as extra_amount,
    mta_tax::number(10, 2)                          as mta_tax_amount,
    tip_amount::number(10, 2)                       as tip_amount,
    tolls_amount::number(10, 2)                     as tolls_amount,
    improvement_surcharge::number(10, 2)            as improvement_surcharge_amount,
    congestion_surcharge::number(10, 2)             as congestion_surcharge_amount,
    airport_fee::number(10, 2)                      as airport_fee_amount,
    cbd_congestion_fee::number(10, 2)               as cbd_congestion_fee_amount,
    total_amount::number(10, 2)                     as total_amount

from source
