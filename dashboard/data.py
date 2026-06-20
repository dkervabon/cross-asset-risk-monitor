"""Snowflake query helpers for the Dash dashboard.

Reads are cached with a short TTL so the app stays responsive without going
stale: the marts are rebuilt by the daily pipeline (not the app), so a cached
read only needs to live long enough to be snappy. Cached entries expire after
CACHE_TTL_SECONDS, and the dashboard's "Refresh data" button calls
clear_caches() to force an immediate re-query after a pipeline run.
"""
import os
import time
from functools import lru_cache, wraps
from pathlib import Path

import pandas as pd
import snowflake.connector
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

CACHE_TTL_SECONDS = 900  # 15 minutes

# registry of TTL-cached functions so clear_caches() can flush them all
_TTL_CACHED = []


def ttl_cache(ttl_seconds: int = CACHE_TTL_SECONDS):
    """Like lru_cache but entries expire after ttl_seconds. Keyed on args."""
    def decorator(fn):
        store: dict = {}

        @wraps(fn)
        def wrapper(*args):
            now = time.time()
            hit = store.get(args)
            if hit is not None and now - hit[1] < ttl_seconds:
                return hit[0]
            value = fn(*args)
            store[args] = (value, now)
            return value

        wrapper.cache_clear = store.clear
        _TTL_CACHED.append(wrapper)
        return wrapper

    return decorator


def clear_caches() -> None:
    """Flush every TTL-cached query (used by the Refresh button)."""
    for fn in _TTL_CACHED:
        fn.cache_clear()

# Friendly names + asset class per ticker, in display order (grouped by class).
# Drives both the heatmap ordering and the ticker-name appendix in the UI.
TICKER_META = [
    ("SPY",      "S&P 500",            "Equity sectors"),
    ("XLF",      "Financials",         "Equity sectors"),
    ("XLE",      "Energy",             "Equity sectors"),
    ("XLK",      "Technology",         "Equity sectors"),
    ("XLV",      "Health Care",        "Equity sectors"),
    ("XLI",      "Industrials",        "Equity sectors"),
    ("XLP",      "Consumer Staples",   "Equity sectors"),
    ("TLT",      "20+ Yr Treasuries",  "Bonds"),
    ("IEF",      "7-10 Yr Treasuries", "Bonds"),
    ("HYG",      "High Yield Credit",  "Bonds"),
    ("GLD",      "Gold",               "Commodities"),
    ("USO",      "Crude Oil",          "Commodities"),
    ("BTC-USD",  "Bitcoin",            "Crypto"),
    ("ETH-USD",  "Ethereum",           "Crypto"),
    ("DX-Y.NYB", "US Dollar Index",    "FX"),
    ("EURUSD=X", "EUR/USD",            "FX"),
]

ASSET_ORDER = [t for t, _, _ in TICKER_META]
TICKER_NAME = {t: name for t, name, _ in TICKER_META}


def _connect():
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        role=os.environ.get("SNOWFLAKE_ROLE") or None,
    )


def _query(sql: str) -> pd.DataFrame:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(sql)
        df = cur.fetch_pandas_all()
        df.columns = [c.lower() for c in df.columns]
        return df
    finally:
        conn.close()


@ttl_cache()
def get_correlation_matrix(window_days: int) -> pd.DataFrame:
    """Symmetric latest-date correlation matrix, ordered by asset class."""
    df = _query(
        f"select ticker_a, ticker_b, correlation "
        f"from MARTS.fct_correlation_matrix_latest where window_days = {window_days}"
    )
    mat = df.pivot(index="ticker_a", columns="ticker_b", values="correlation")
    order = [t for t in ASSET_ORDER if t in mat.index]
    return mat.reindex(index=order, columns=order)


@lru_cache(maxsize=1)
def get_tickers() -> tuple:
    return tuple(ASSET_ORDER)


@ttl_cache()
def get_pair_history(ticker_a: str, ticker_b: str) -> pd.DataFrame:
    """Rolling correlation time series (both windows) for one pair, either ordering."""
    lo, hi = sorted([ticker_a, ticker_b])
    return _query(
        f"select price_date, window_days, correlation "
        f"from MARTS.fct_rolling_correlations "
        f"where ticker_a = '{lo}' and ticker_b = '{hi}' "
        f"order by price_date"
    )


@ttl_cache()
def get_stress_regimes(window_days: int) -> pd.DataFrame:
    return _query(
        f"select price_date, avg_corr, corr_dispersion, corr_zscore, regime "
        f"from MARTS.fct_stress_regimes where window_days = {window_days} "
        f"order by price_date"
    )


@ttl_cache()
def get_decoupling_latest(window_days: int) -> pd.DataFrame:
    """Most recent day's per-asset decoupling leaderboard."""
    return _query(
        f"""
        with latest as (
            select max(price_date) d from MARTS.fct_decoupling_flags
            where window_days = {window_days}
        )
        select price_date, decoupling_rank, ticker, asset_avg_corr, baseline_corr,
               decoupling_score, decoupling_zscore, decoupling_flag, contagion_flag
        from MARTS.fct_decoupling_flags, latest
        where window_days = {window_days} and price_date = latest.d
        order by decoupling_rank
        """
    )


@ttl_cache()
def get_latest_date(window_days: int) -> str:
    df = _query(
        f"select max(price_date) d from MARTS.fct_correlation_matrix_latest "
        f"where window_days = {window_days}"
    )
    return str(df["d"].iloc[0])
