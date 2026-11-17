select
    reading_key,
    site_id,
    detector_id,
    interval_end,
    interval_end - interval 15 minute as interval_start,
    -- interval_end is UTC without a zone; convert the interval start to local wall-clock time.
    ((interval_end - interval 15 minute) at time zone 'UTC') at time zone '{{ var("local_time_zone") }}' as local_interval_start,
    volume,
    source
from {{ ref('stg_readings') }}
