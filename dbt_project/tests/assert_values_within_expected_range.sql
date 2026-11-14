{{ config(tags=['staging']) }}
-- Fails (returns rows) for any value outside the guard-rail range in seeds/indicator_ranges.csv.
select o.source_id, o.country_code, o.year, o.value, r.min_value, r.max_value
from {{ ref('stg_world_bank_observations') }} o
join {{ ref('indicator_ranges') }} r on r.source_id = o.source_id
where o.value < r.min_value or o.value > r.max_value
