{% test raw_no_negative_volume(model) %}
-- The API rejects negative volumes, so any negative value in the raw table is a fault.
select site_id, detector_id, interval_end, volume
from {{ model }}
where volume < 0
{% endtest %}
