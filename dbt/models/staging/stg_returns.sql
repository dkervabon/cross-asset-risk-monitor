-- Daily log returns per ticker, aligned to the US equity (SPY) trading calendar.
--
-- Crypto trades 7 days/week and FX on a slightly different calendar; if we computed
-- returns on each asset's native calendar, a Monday crypto return (Sun->Mon, 1 day)
-- would be compared against a Monday equity return (Fri->Mon, 3 days). Restricting
-- every asset to SPY's trading dates makes each return span the same interval, which
-- is required for honest cross-asset correlation.
with prices as (
    select * from {{ ref('stg_prices') }}
),

calendar as (
    select distinct price_date
    from prices
    where ticker = 'SPY'
),

aligned as (
    select p.*
    from prices p
    inner join calendar c on p.price_date = c.price_date
),

returns as (
    select
        ticker,
        asset_name,
        asset_class,
        price_date,
        adj_close,
        ln(
            adj_close
            / nullif(lag(adj_close) over (partition by ticker order by price_date), 0)
        ) as log_return
    from aligned
)

select *
from returns
where log_return is not null
