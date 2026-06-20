-- Rolling Pearson correlation per asset pair, for 30- and 90-trading-day windows.
--
-- Snowflake's CORR() is an aggregate, not a sliding-window function, so we compute
-- Pearson from windowed sums:
--   corr = (n*Sxy - Sx*Sy) / sqrt((n*Sxx - Sx^2) * (n*Syy - Sy^2))
-- A correlation is only emitted once the trailing window is completely full (n = window),
-- so early, partial windows are dropped rather than reported as noisy estimates.
with paired as (
    select * from {{ ref('int_returns_paired') }}
),

w30_raw as (
    select
        price_date, ticker_a, ticker_b,
        30 as window_days,
        count(*)               over (partition by ticker_a, ticker_b order by price_date rows between 29 preceding and current row) as n,
        sum(return_a)          over (partition by ticker_a, ticker_b order by price_date rows between 29 preceding and current row) as sx,
        sum(return_b)          over (partition by ticker_a, ticker_b order by price_date rows between 29 preceding and current row) as sy,
        sum(return_a*return_a) over (partition by ticker_a, ticker_b order by price_date rows between 29 preceding and current row) as sxx,
        sum(return_b*return_b) over (partition by ticker_a, ticker_b order by price_date rows between 29 preceding and current row) as syy,
        sum(return_a*return_b) over (partition by ticker_a, ticker_b order by price_date rows between 29 preceding and current row) as sxy
    from paired
),

w90_raw as (
    select
        price_date, ticker_a, ticker_b,
        90 as window_days,
        count(*)               over (partition by ticker_a, ticker_b order by price_date rows between 89 preceding and current row) as n,
        sum(return_a)          over (partition by ticker_a, ticker_b order by price_date rows between 89 preceding and current row) as sx,
        sum(return_b)          over (partition by ticker_a, ticker_b order by price_date rows between 89 preceding and current row) as sy,
        sum(return_a*return_a) over (partition by ticker_a, ticker_b order by price_date rows between 89 preceding and current row) as sxx,
        sum(return_b*return_b) over (partition by ticker_a, ticker_b order by price_date rows between 89 preceding and current row) as syy,
        sum(return_a*return_b) over (partition by ticker_a, ticker_b order by price_date rows between 89 preceding and current row) as sxy
    from paired
),

combined as (
    select * from w30_raw where n = 30
    union all
    select * from w90_raw where n = 90
)

select
    md5(ticker_a || '-' || ticker_b || '-' || window_days || '-' || price_date) as corr_key,
    price_date,
    ticker_a,
    ticker_b,
    window_days,
    (n*sxy - sx*sy)
        / nullif(sqrt((n*sxx - sx*sx) * (n*syy - sy*sy)), 0) as correlation
from combined
