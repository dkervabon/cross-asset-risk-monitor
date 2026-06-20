"""Snowflake query helpers for the Dash dashboard.

A tiny in-process cache keeps the app responsive — the marts are rebuilt by dbt,
not by the app, so caching reads for the session is safe.
"""
import os
from functools import lru_cache
from pathlib import Path

import pandas as pd
import snowflake.connector
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

# Display order + friendly names, grouped by asset class for a readable heatmap.
ASSET_ORDER = [
    "SPY", "XLF", "XLE", "XLK", "XLV", "XLI", "XLP",   # equity sectors
    "TLT", "IEF", "HYG",                                # bonds
    "GLD", "USO",                                       # commodities
    "BTC-USD", "ETH-USD",                               # crypto
    "DX-Y.NYB", "EURUSD=X",                             # fx
]


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


@lru_cache(maxsize=8)
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


@lru_cache(maxsize=64)
def get_pair_history(ticker_a: str, ticker_b: str) -> pd.DataFrame:
    """Rolling correlation time series (both windows) for one pair, either ordering."""
    lo, hi = sorted([ticker_a, ticker_b])
    return _query(
        f"select price_date, window_days, correlation "
        f"from MARTS.fct_rolling_correlations "
        f"where ticker_a = '{lo}' and ticker_b = '{hi}' "
        f"order by price_date"
    )


@lru_cache(maxsize=4)
def get_stress_regimes(window_days: int) -> pd.DataFrame:
    return _query(
        f"select price_date, avg_corr, corr_dispersion, corr_zscore, regime "
        f"from MARTS.fct_stress_regimes where window_days = {window_days} "
        f"order by price_date"
    )


@lru_cache(maxsize=8)
def get_decoupling_latest(window_days: int) -> pd.DataFrame:
    """Most recent day's per-asset decoupling leaderboard."""
    return _query(
        f"""
        with latest as (
            select max(price_date) d from MARTS.fct_decoupling_flags
            where window_days = {window_days}
        )
        select decoupling_rank, ticker, asset_avg_corr, baseline_corr,
               decoupling_score, decoupling_zscore, decoupling_flag, contagion_flag
        from MARTS.fct_decoupling_flags, latest
        where window_days = {window_days} and price_date = latest.d
        order by decoupling_rank
        """
    )


def get_latest_date(window_days: int) -> str:
    df = _query(
        f"select max(price_date) d from MARTS.fct_correlation_matrix_latest "
        f"where window_days = {window_days}"
    )
    return str(df["d"].iloc[0])
