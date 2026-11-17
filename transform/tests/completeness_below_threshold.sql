-- Singular test: fails when more than var('max_incomplete_share') of detector-days have fewer
-- intervals than var('min_completeness') (decisions D45). The Python completeness check lists them.
with health as (
    select completeness from {{ ref('fct_detector_health') }}
),

summary as (
    select
        count(*) as detector_days,
        count(*) filter (where completeness < {{ var('min_completeness') }}) as below
    from health
)

select detector_days, below, below / detector_days as share_below
from summary
where below > detector_days * {{ var('max_incomplete_share') }}
