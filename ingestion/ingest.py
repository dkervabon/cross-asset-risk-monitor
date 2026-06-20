"""Download daily price history from yfinance and load it into Snowflake RAW.PRICES.

Idempotent: rebuilds the RAW.PRICES table on each run (full refresh of 10y history).

Usage:
    python ingestion/ingest.py
"""
import sys
import time

import pandas as pd
import yfinance as yf
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas

from config import (
    ASSETS,
    TICKERS,
    HISTORY_PERIOD,
    RAW_SCHEMA,
    RAW_TABLE,
    snowflake_params,
)


def download_prices() -> pd.DataFrame:
    """Download adjusted-close + volume for every ticker into a long DataFrame."""
    frames = []
    for ticker in TICKERS:
        name, asset_class = ASSETS[ticker]
        for attempt in range(3):
            try:
                hist = yf.Ticker(ticker).history(
                    period=HISTORY_PERIOD, auto_adjust=True, raise_errors=False
                )
                break
            except Exception as e:  # transient network / rate limit
                print(f"  retry {ticker} ({attempt+1}/3): {e}")
                time.sleep(2 * (attempt + 1))
        else:
            print(f"  !! FAILED to download {ticker}, skipping")
            continue

        if hist is None or hist.empty:
            print(f"  !! no data for {ticker}, skipping")
            continue

        df = hist[["Close", "Volume"]].reset_index()
        df.columns = ["DATE", "ADJ_CLOSE", "VOLUME"]
        # yfinance returns tz-aware timestamps; normalize to plain dates.
        df["DATE"] = pd.to_datetime(df["DATE"]).dt.tz_localize(None).dt.normalize()
        df["TICKER"] = ticker
        df["NAME"] = name
        df["ASSET_CLASS"] = asset_class
        df = df.dropna(subset=["ADJ_CLOSE"])
        frames.append(df)
        print(f"  {ticker:10s} {len(df):5d} rows  ({df['DATE'].min().date()} -> {df['DATE'].max().date()})")

    if not frames:
        sys.exit("No data downloaded for any ticker — aborting.")

    out = pd.concat(frames, ignore_index=True)
    out = out[["DATE", "TICKER", "NAME", "ASSET_CLASS", "ADJ_CLOSE", "VOLUME"]]
    # Send dates as ISO strings; write_pandas mis-scales native datetime values,
    # but Snowflake reliably casts 'YYYY-MM-DD' strings into a DATE column.
    out["DATE"] = out["DATE"].dt.strftime("%Y-%m-%d")
    out["ADJ_CLOSE"] = out["ADJ_CLOSE"].astype(float)
    out["VOLUME"] = out["VOLUME"].fillna(0).astype("int64")
    return out


def load_to_snowflake(df: pd.DataFrame) -> None:
    """Full-refresh load into RISK_MONITOR.<RAW_SCHEMA>.PRICES."""
    params = snowflake_params()
    conn = snowflake.connector.connect(**params)
    cur = conn.cursor()
    cur.execute(f"USE DATABASE {params['database']}")
    cur.execute(f"USE SCHEMA {RAW_SCHEMA}")
    cur.execute(
        f"""
        CREATE OR REPLACE TABLE {RAW_TABLE} (
            DATE         DATE       NOT NULL,
            TICKER       VARCHAR    NOT NULL,
            NAME         VARCHAR,
            ASSET_CLASS  VARCHAR,
            ADJ_CLOSE    FLOAT      NOT NULL,
            VOLUME       NUMBER(38,0)
        )
        """
    )
    success, n_chunks, n_rows, _ = write_pandas(
        conn, df, RAW_TABLE, schema=RAW_SCHEMA, database=params["database"],
        quote_identifiers=False,
    )
    print(f"\nwrite_pandas: success={success}  rows={n_rows}  chunks={n_chunks}")

    cur.execute(f"SELECT COUNT(*), MIN(DATE), MAX(DATE), COUNT(DISTINCT TICKER) FROM {RAW_TABLE}")
    print("RAW.PRICES now:", cur.fetchone())
    cur.close()
    conn.close()


def main() -> None:
    print(f"Downloading {HISTORY_PERIOD} of history for {len(TICKERS)} tickers...")
    df = download_prices()
    print(f"\nTotal rows: {len(df)}  | tickers loaded: {df['TICKER'].nunique()}")
    print("Loading to Snowflake...")
    load_to_snowflake(df)
    print("Done.")


if __name__ == "__main__":
    main()
