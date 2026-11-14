-- Every time the source returned a different value for a year we already had.
-- Possible because the raw layer keeps every load instead of overwriting.
with history as (
    select
        source_id,
        upper(trim(country)) as country_code,
        year,
        value,
        loaded_at,
        lag(value) over (
            partition by source_id, upper(trim(country)), year
            order by loaded_at
        ) as previous_value
    from {{ source('raw', 'world_bank_observations') }}
    where value is not null
)

select
    source_id,
    country_code,
    year,
    previous_value,
    value,
    value - previous_value as revision,
    loaded_at
from history
where previous_value is not null
  and abs(value - previous_value) > 0.000000001
