{% test raw_duplicate_rate_within_limit(model) %}
-- Fails (returns one row) when more than var('max_duplicate_rate') of raw rows repeat a key.
with counts as (
    select count(*) as total, count(distinct site_id || '|' || detector_id || '|' || interval_end) as distinct_keys
    from {{ model }}
)
select total, distinct_keys, (total - distinct_keys) * 1.0 / total as duplicate_rate
from counts
where total > 0 and (total - distinct_keys) * 1.0 / total > {{ var('max_duplicate_rate') }}
{% endtest %}
