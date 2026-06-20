-- Per-asset decoupling / contagion signal: which assets pull away from the pack first.
--
-- For each asset we compute its average correlation to every other asset ("how tied is
-- this asset to the system right now"), then compare it to that asset's own trailing
-- 60-day baseline. A sharp drop (negative z-score) means the asset is decoupling; the
-- daily rank surfaces *which* asset decouples first. Conversely a sharp rise flags an
-- asset getting pulled into a contagion regime.
with corr as (
    select price_date, ticker_a, ticker_b, window_days, correlation
    from {{ ref('fct_rolling_correlations') }}
),

-- expand each unordered pair into both directions so every asset is a focal "ticker"
directed as (
    select price_date, window_days, ticker_a as ticker, correlation from corr
    union all
    select price_date, window_days, ticker_b as ticker, correlation from corr
),

asset_corr as (
    select
        price_date,
        window_days,
        ticker,
        avg(correlation) as asset_avg_corr
    from directed
    group by 1, 2, 3
),

baseline as (
    select
        *,
        avg(asset_avg_corr) over (
            partition by ticker, window_days order by price_date
            rows between 60 preceding and 1 preceding
        ) as baseline_corr,
        stddev(asset_avg_corr) over (
            partition by ticker, window_days order by price_date
            rows between 60 preceding and 1 preceding
        ) as baseline_std
    from asset_corr
),

scored as (
    select
        *,
        asset_avg_corr - baseline_corr as decoupling_score,
        (asset_avg_corr - baseline_corr) / nullif(baseline_std, 0) as decoupling_zscore
    from baseline
)

select
    price_date,
    window_days,
    ticker,
    asset_avg_corr,
    baseline_corr,
    decoupling_score,
    decoupling_zscore,
    -- rank 1 = the asset decoupling most sharply (largest correlation drop) that day
    rank() over (
        partition by price_date, window_days
        order by decoupling_zscore asc
    ) as decoupling_rank,
    case when decoupling_zscore <= -1.5 then true else false end as decoupling_flag,
    case when decoupling_zscore >=  1.5 then true else false end as contagion_flag
from scored
where baseline_corr is not null
