-- One row per reading key (site, detector, interval end). A repeat keeps the earliest load.
with ranked as (
    select
        site_id,
        detector_id,
        interval_end,
        volume,
        source,
        _object_key,
        _loaded_at,
        row_number() over (
            partition by site_id, detector_id, interval_end
            order by _loaded_at, _object_key
        ) as rn
    from {{ source('raw', 'readings') }}
)

select
    site_id || '|' || detector_id || '|' || strftime(interval_end, '%Y-%m-%dT%H:%M:%SZ') as reading_key,
    site_id,
    detector_id,
    interval_end,
    volume,
    source
from ranked
where rn = 1
