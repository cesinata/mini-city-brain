-- Singular test: fails for every detector-day with fewer intervals than var('min_completeness').
select site_id, detector_id, local_date, intervals_observed, completeness
from {{ ref('fct_detector_health') }}
where completeness < {{ var('min_completeness') }}
