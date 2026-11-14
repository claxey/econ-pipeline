-- One row per indicator, country and year: the LATEST value the source returned.
-- Rows the source returned as null are dropped here, so a value the provider removed disappears.
with ranked as (
    select
        source_id,
        upper(trim(country)) as country_code,
        year,
        value,
        loaded_at,
        row_number() over (
            partition by source_id, upper(trim(country)), year
            order by loaded_at desc, run_id desc
        ) as rn
    from {{ source('raw', 'world_bank_observations') }}
)

select
    source_id,
    country_code,
    year,
    cast(value as numeric(18, 6)) as value,
    loaded_at as last_loaded_at
from ranked
where rn = 1
  and value is not null
