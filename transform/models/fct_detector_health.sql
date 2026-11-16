-- Completeness = observed 15-minute intervals / 96, per detector and local day.
-- The reading schema carries no alarm field, so alarms are not part of this table (D26).
select
    site_id,
    detector_id,
    cast(local_interval_start as date) as local_date,
    count(*) as intervals_observed,
    96 as intervals_expected,
    round(count(*) / 96.0, 4) as completeness,
    sum(volume) as volume_24h,
    min(source) as source
from {{ ref('fct_volume_15min') }}
group by 1, 2, 3
