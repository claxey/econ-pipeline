-- Cleaned yearly series with a few derived measures (window functions).
-- change_vs_prev_year is only filled when the previous row really is the previous calendar year.
with base as (
    select
        source_id,
        country_code,
        year,
        value,
        lag(value) over (partition by source_id, country_code order by year) as prev_value,
        lag(year)  over (partition by source_id, country_code order by year) as prev_year,
        avg(value) over (
            partition by source_id, country_code
            order by year
            rows between 4 preceding and current row
        ) as avg_last_5_rows,
        count(*) over (
            partition by source_id, country_code
            order by year
            rows between 4 preceding and current row
        ) as rows_in_window
    from {{ ref('stg_world_bank_observations') }}
)

select
    source_id,
    country_code,
    year,
    value,
    case when year - prev_year = 1 then value - prev_value end as change_vs_prev_year,
    case when rows_in_window = 5 then avg_last_5_rows end as avg_last_5_years
from base
