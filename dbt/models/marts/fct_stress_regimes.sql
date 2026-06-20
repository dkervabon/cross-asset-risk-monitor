-- Systemic stress regime per day, per window.
--
-- In a crisis, cross-asset correlations collapse toward 1 ("everything moves together").
-- We track the daily *average* pairwise correlation and its dispersion, then z-score the
-- average against its trailing 1-year (252-trading-day) distribution. High z = correlations
-- abnormally elevated = systemic stress; low z = unusually decoupled / calm.
with corr as (
    select * from {{ ref('fct_rolling_correlations') }}
),

daily as (
    select
        price_date,
        window_days,
        avg(correlation)     as avg_corr,
        stddev(correlation)  as corr_dispersion,
        min(correlation)     as min_corr,
        max(correlation)     as max_corr,
        count(*)             as n_pairs
    from corr
    group by 1, 2
),

stats as (
    select
        *,
        avg(avg_corr) over (
            partition by window_days order by price_date
            rows between 251 preceding and current row
        ) as roll_mean,
        stddev(avg_corr) over (
            partition by window_days order by price_date
            rows between 251 preceding and current row
        ) as roll_std,
        count(*) over (
            partition by window_days order by price_date
            rows between 251 preceding and current row
        ) as roll_n
    from daily
),

scored as (
    select
        *,
        case when roll_n >= 60
             then (avg_corr - roll_mean) / nullif(roll_std, 0)
        end as corr_zscore
    from stats
)

select
    price_date,
    window_days,
    avg_corr,
    corr_dispersion,
    min_corr,
    max_corr,
    n_pairs,
    roll_mean,
    roll_std,
    corr_zscore,
    case
        when corr_zscore is null  then 'WARMUP'
        when corr_zscore >= 1.0   then 'STRESS'
        when corr_zscore <= -1.0  then 'CALM'
        else 'NORMAL'
    end as regime
from scored
