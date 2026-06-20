# Cross-Asset Risk Monitor

> When cross-asset correlations break down, which assets decouple first and which follow — and can we identify systemic stress regimes in real time?

An end-to-end data engineering project that ingests daily prices across equities, bonds, commodities, crypto, and FX, computes rolling cross-asset correlations in Snowflake via dbt, detects systemic **stress regimes**, ranks which assets **decouple first**, and visualizes it all in an interactive dashboard.

## The analytical idea

In normal markets, asset classes move on their own fundamentals and pairwise correlations are moderate. In a crisis, diversification fails: correlations across everything spike toward **+1** ("risk-on / risk-off"). This project quantifies that in two complementary ways:

1. **Systemic stress regimes** — the daily *average* pairwise correlation across all 16 assets, z-scored against its trailing 1-year distribution. A high z-score = correlations abnormally elevated = systemic stress.
2. **Decoupling / contagion ranking** — for each asset, its average correlation to the rest vs its own 60-day baseline. A sharp drop flags the asset *decoupling first*; a sharp rise flags it being pulled into a contagion regime. A daily rank answers "which moved first."

The output correctly surfaces known events — the COVID crash, the 2022 rate-hike bear market, the Sept 2022 dollar surge (the US Dollar Index decoupled first), and the April 2025 tariff shock.

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

## Data quality

dbt ships 24 tests: source/column `not_null`, primary-key `unique`, `accepted_values` for window sizes and regime labels, and a singular test asserting every correlation lies in [-1, 1].

## Notes

- **Secrets** live in `.env` (gitignored). Nothing sensitive is committed.
- ETH-USD history begins ~Aug 2017; earlier dates are simply absent for that asset.
- The pipeline is a full refresh and is safe to re-run; `ingest.py` rebuilds `RAW.PRICES` and `dbt build` rebuilds all marts.
