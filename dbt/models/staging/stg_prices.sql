-- Cleaned daily prices, one row per (ticker, trading date).
with source as (
    select * from {{ source('raw', 'prices') }}
)

select
    date::date            as price_date,
    ticker,
    name                  as asset_name,
    asset_class,
    adj_close,
    volume
from source
where adj_close is not null
  and adj_close > 0
