# Cross-Asset Risk Monitor

Dashboard hosted on Render free tier — may take 30–60 seconds to wake on first load.

**🔗 Live dashboard: [cross-asset-risk-monitor.onrender.com](https://cross-asset-risk-monitor.onrender.com)**

[![Daily pipeline](https://github.com/dkervabon/cross-asset-risk-monitor/actions/workflows/daily-ingest.yml/badge.svg)](https://github.com/dkervabon/cross-asset-risk-monitor/actions/workflows/daily-ingest.yml)

> When cross-asset correlations break down, which assets decouple first and which follow — and can we identify systemic stress regimes in real time?

An end-to-end data engineering project that ingests daily prices across equities, bonds, commodities, crypto, and FX, computes rolling cross-asset correlations in Snowflake via dbt, detects systemic **stress regimes**, ranks which assets **decouple first**, and visualizes it all in an interactive dashboard.

## The analytical idea

In normal markets, asset classes move on their own fundamentals and pairwise correlations are moderate. In a crisis, diversification fails: correlations across everything spike toward **+1** ("risk-on / risk-off"). This project quantifies that in two complementary ways:

1. **Systemic stress regimes** — the daily *average* pairwise correlation across all 16 assets, z-scored against its trailing 1-year distribution. A high z-score = correlations abnormally elevated = systemic stress.
2. **Decoupling / contagion ranking** — for each asset, its average correlation to the rest vs its own 60-day baseline. A sharp drop flags the asset *decoupling first*; a sharp rise flags it being pulled into a contagion regime. A daily rank answers "which moved first."

The output correctly surfaces known events — the COVID crash, the 2022 rate-hike bear market, the Sept 2022 dollar surge (the US Dollar Index decoupled first), and the April 2025 tariff shock.

## Key Findings

**1. Cross-asset diversification collapsed during the COVID crash**

The average pairwise correlation across all 16 assets spiked from ~0.13 in calm 2019 to a peak of **0.31 on March 12, 2020 — 7.97 standard deviations** above its trailing-year norm, the most extreme reading in the entire 10-year window. As correlations converged, assets that normally offset each other fell together — the textbook signature of a systemic stress regime. Over the full period, 23% of trading days register as STRESS by this measure (90-day window).

**2. The US dollar decoupled first during the 2022 rate-hike cycle**

Ranking each asset daily by how sharply its correlation-to-the-market breaks from its own 60-day baseline, the **US Dollar Index (DX-Y.NYB) was the #1 decoupler on 68 trading days in 2022** — more than any other asset (EUR/USD was second at 57). As the Fed hiked aggressively, the resulting dollar surge pulled it away from a market where equities, bonds, and credit were increasingly falling together.

**3. The classic stock/bond hedge inverted in the high-rate era**

The 90-day SPY vs TLT correlation swung from a decade low of **−0.63 (March 10, 2020)**, when Treasuries rallied as equities crashed, to a high of **+0.41 (November 14, 2023)** — flipping from a strong hedge to positive co-movement. Bonds stopped protecting against equity drawdowns once rate risk, rather than growth risk, became the dominant market driver.

## Architecture

```
yfinance ──> Snowflake RAW ──> dbt (staging → intermediate → marts) ──> Dash
 (Python)      (PRICES)        correlations / regimes / decoupling      (Plotly)
```

| Layer | Tech | What it does |
|-------|------|--------------|
| Ingestion | Python, `yfinance` | 10y daily adj-close + volume for 16 tickers → `RAW.PRICES` |
| Storage | Snowflake | `RISK_MONITOR` database, `RAW` / `STAGING` / `MARTS` schemas |
| Transform | dbt Core + dbt-snowflake | returns, rolling correlations, regimes, decoupling flags |
| Viz | Dash + Plotly | heatmap, rolling-correlation charts, regime timeline, decoupling leaderboard |

## Asset universe (16)

- **US equity sectors:** SPY, XLF, XLE, XLK, XLV, XLI, XLP
- **Bonds:** TLT, IEF, HYG
- **Commodities:** GLD, USO
- **Crypto:** BTC-USD, ETH-USD
- **FX:** DX-Y.NYB, EURUSD=X

## dbt models

```
staging/
  stg_prices            cleaned daily prices
  stg_returns           log returns, aligned to the SPY trading calendar*
intermediate/
  int_returns_paired    every unordered asset pair's returns on common dates (120 pairs)
marts/
  fct_rolling_correlations      rolling 30d & 90d Pearson corr per pair
  fct_stress_regimes            daily avg corr, z-score, regime label
  fct_decoupling_flags          per-asset decoupling/contagion z-score + daily rank
  fct_correlation_matrix_latest symmetric matrix for the latest date (heatmap source)
```

\* *Crypto trades 7 days/week and FX on a different calendar. Returns are aligned to SPY's trading dates so every asset's daily return spans the same interval — required for honest cross-asset correlation.*

Correlation is computed from windowed sums (Snowflake's `CORR()` is not a sliding-window function):
`corr = (n·Σxy − Σx·Σy) / √((n·Σx² − (Σx)²)(n·Σy² − (Σy)²))`, emitted only once the window is full.

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure credentials
cp .env.example .env        # then edit .env with your Snowflake account

# 3. Ingest 10 years of prices into Snowflake RAW.PRICES
python ingestion/ingest.py

# 4. Build the dbt models + run tests
cd dbt
set -a && . ../.env && set +a          # export creds for dbt env_var()
export DBT_PROFILES_DIR="$(pwd)"
dbt build

# 5. Launch the dashboard
cd ..
python dashboard/app.py                 # http://127.0.0.1:8050
```

Or run the whole pipeline (ingest + dbt) with `./run_pipeline.sh`.

## Orchestration

A scheduled GitHub Actions workflow ([`.github/workflows/daily-ingest.yml`](.github/workflows/daily-ingest.yml)) runs the full pipeline once a day, after the US market close:

1. **EL** — `ingest.py` full-refreshes `RAW.PRICES` from yfinance
2. **T** — `dbt build` rebuilds and tests every model

**Schedule.** GitHub cron runs in UTC and ignores daylight saving, so the workflow fires at both 22:00 and 23:00 UTC on weekdays, and a `gate` job admits only the trigger where the local time is actually 18:00 `America/New_York` — exactly 6pm ET year-round, with no double-runs. Manual runs are available via the **Run workflow** button (they skip the time gate).

**Credentials.** The workflow reads Snowflake credentials from GitHub Actions secrets — add these under *Settings → Secrets and variables → Actions*:

```
SNOWFLAKE_ACCOUNT   SNOWFLAKE_USER       SNOWFLAKE_PASSWORD
SNOWFLAKE_DATABASE  SNOWFLAKE_WAREHOUSE  SNOWFLAKE_ROLE
```

`dbt/profiles.yml` is committed but contains only `env_var()` references, so no credentials ever live in the repo.

## Data quality

dbt ships 24 tests: source/column `not_null`, primary-key `unique`, `accepted_values` for window sizes and regime labels, and a singular test asserting every correlation lies in [-1, 1].

## Notes

- **Secrets** live in `.env` locally (gitignored) and in GitHub Actions secrets for CI. Nothing sensitive is committed.
- ETH-USD history begins ~Aug 2017; earlier dates are simply absent for that asset.
- The pipeline is a full refresh and is safe to re-run; `ingest.py` rebuilds `RAW.PRICES` and `dbt build` rebuilds all marts.
- The dashboard caches Snowflake reads with a 15-minute TTL and has a **Refresh data** button to flush the cache on demand, so it reflects new pipeline runs without a restart.
