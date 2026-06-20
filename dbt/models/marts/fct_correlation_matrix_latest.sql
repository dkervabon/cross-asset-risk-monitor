-- Full symmetric correlation matrix for the most recent date, per window.
-- Feeds the Dash heatmap directly: both directions of each pair plus a 1.0 diagonal.
with corr as (
    select * from {{ ref('fct_rolling_correlations') }}
),

latest as (
    select window_days, max(price_date) as price_date
    from corr
    group by window_days
),

both_directions as (
    select c.price_date, c.window_days, c.ticker_a, c.ticker_b, c.correlation
    from corr c
    join latest l
      on c.window_days = l.window_days and c.price_date = l.price_date
    union all
    select c.price_date, c.window_days, c.ticker_b as ticker_a, c.ticker_a as ticker_b, c.correlation
    from corr c
    join latest l
      on c.window_days = l.window_days and c.price_date = l.price_date
),

all_tickers as (
    select distinct window_days, ticker_a as ticker from both_directions
),

diagonal as (
    select l.price_date, t.window_days, t.ticker as ticker_a, t.ticker as ticker_b, 1.0 as correlation
    from all_tickers t
    join latest l on t.window_days = l.window_days
)

select * from both_directions
union all
select * from diagonal
