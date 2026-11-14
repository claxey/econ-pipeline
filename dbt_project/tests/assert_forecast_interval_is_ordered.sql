{{ config(tags=['reporting']) }}
-- Fails if a forecast's lower bound is above its forecast or its upper bound.
select source_id, country_code, forecast_year, forecast_lower, forecast_value, forecast_upper
from {{ ref('rpt_latest_indicators') }}
where forecast_lower is not null
  and (forecast_lower > forecast_value or forecast_value > forecast_upper)
