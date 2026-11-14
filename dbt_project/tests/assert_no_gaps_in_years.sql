{{ config(tags=['staging'], severity='warn') }}
-- Warns when a series skips a year between its first and last value.
select source_id, country_code, min(year) as first_year, max(year) as last_year, count(*) as n_years
from {{ ref('stg_world_bank_observations') }}
group by source_id, country_code
having count(*) < max(year) - min(year) + 1
