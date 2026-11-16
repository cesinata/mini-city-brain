-- Vehicles per site per local hour: the sum over detectors and intervals present.
select
    site_id,
    date_trunc('hour', local_interval_start) as local_hour,
    cast(local_interval_start as date) as local_date,
    extract(hour from local_interval_start)::integer as hour_of_day,
    extract(isodow from local_interval_start)::integer as iso_weekday,
    sum(volume) as volume,
    count(*) as intervals_observed,
    count(distinct detector_id) as detectors_reporting,
    min(source) as source
from {{ ref('fct_volume_15min') }}
group by 1, 2, 3, 4, 5
