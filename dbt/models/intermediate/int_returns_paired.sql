-- One row per unordered asset pair per date, carrying both assets' returns on
-- that common date. ticker_a < ticker_b keeps each pair once (C(16,2) = 120 pairs).
with r as (
    select ticker, price_date, log_return
    from {{ ref('stg_returns') }}
)

select
    a.price_date,
    a.ticker      as ticker_a,
    b.ticker      as ticker_b,
    a.log_return  as return_a,
    b.log_return  as return_b
from r a
join r b
  on a.price_date = b.price_date
 and a.ticker < b.ticker
