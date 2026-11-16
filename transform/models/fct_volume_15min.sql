select
    reading_key,
    site_id,
    detector_id,
    interval_end,
    interval_end - interval 15 minute as interval_start,
    interval_end - interval 15 minute + to_hours({{ var('local_offset_hours') }}) as local_interval_start,
    volume,
    source
from {{ ref('stg_readings') }}
