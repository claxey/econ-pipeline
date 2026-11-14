select
    source_id,
    name as indicator_name,
    provider,
    indicator_code,
    docs_url,
    frequency
from {{ source('raw', 'source_catalog') }}
