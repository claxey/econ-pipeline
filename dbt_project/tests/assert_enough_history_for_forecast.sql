{{ config(tags=['staging'], severity='warn') }}
-- Warns for any series with fewer than 12 yearly values, because the forecast step skips those.
select source_id, country_code, count(*) as n_years
from {{ ref('stg_world_bank_observations') }}
group by source_id, country_code
having count(*) < 12
