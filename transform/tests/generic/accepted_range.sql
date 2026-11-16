{% test accepted_range(model, column_name, min_value, max_value) %}
-- Fails for every row outside [min_value, max_value].
select {{ column_name }} as bad_value
from {{ model }}
where {{ column_name }} < {{ min_value }} or {{ column_name }} > {{ max_value }}
{% endtest %}
