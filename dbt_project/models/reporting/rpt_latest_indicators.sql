-- FINAL REPORTING TABLE: one row per indicator and country, ready for a dashboard or a report.
with latest_year as (
    select source_id, country_code, max(year) as year
    from {{ ref('fct_indicator_yearly') }}
    group by source_id, country_code
),

latest as (
    select y.*
    from {{ ref('fct_indicator_yearly') }} y
    join latest_year l
      on l.source_id = y.source_id
     and l.country_code = y.country_code
     and l.year = y.year
),

latest_forecast as (
    select source_id, country_code, year, forecast, lower, upper, model
    from {{ source('forecasts', 'indicator_forecasts') }}
    where created_at = (select max(created_at) from {{ source('forecasts', 'indicator_forecasts') }})
)

select
    i.indicator_name,
    l.source_id,
    c.country_name,
    l.country_code,
    l.year as latest_year,
    l.value as latest_value,
    l.change_vs_prev_year,
    l.avg_last_5_years,
    rank() over (partition by l.source_id order by l.value desc) as rank_among_countries,
    f.year as forecast_year,
    f.forecast as forecast_value,
    f.lower as forecast_lower,
    f.upper as forecast_upper,
    f.model as forecast_model
from latest l
join {{ ref('dim_indicator') }} i on i.source_id = l.source_id
join {{ ref('dim_country') }} c on c.country_code = l.country_code
left join latest_forecast f
       on f.source_id = l.source_id
      and f.country_code = l.country_code
      and f.year = l.year + 1
