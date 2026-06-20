"""Asset universe and Snowflake connection config for the Cross-Asset Risk Monitor."""
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root regardless of where the script is invoked.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

# How much daily history to pull.
HISTORY_PERIOD = "10y"

# Asset universe: ticker -> (human name, asset class).
# Tickers are yfinance symbols; some contain characters that aren't valid in
# Snowflake column/identifier names, so we store ticker as a value, not a column.
ASSETS = {
    # US equity sectors
    "SPY":      ("S&P 500",                 "equity"),
    "XLF":      ("Financials",              "equity"),
    "XLE":      ("Energy",                  "equity"),
    "XLK":      ("Technology",              "equity"),
    "XLV":      ("Health Care",             "equity"),
    "XLI":      ("Industrials",             "equity"),
    "XLP":      ("Consumer Staples",        "equity"),
    # Bonds
    "TLT":      ("20+ Yr Treasuries",       "bond"),
    "IEF":      ("7-10 Yr Treasuries",      "bond"),
    "HYG":      ("High Yield Credit",       "bond"),
    # Commodities
    "GLD":      ("Gold",                    "commodity"),
    "USO":      ("Crude Oil",               "commodity"),
    # Crypto
    "BTC-USD":  ("Bitcoin",                 "crypto"),
    "ETH-USD":  ("Ethereum",                "crypto"),
    # FX
    "DX-Y.NYB": ("US Dollar Index",         "fx"),
    "EURUSD=X": ("EUR/USD",                 "fx"),
}

TICKERS = list(ASSETS.keys())


def snowflake_params() -> dict:
    """Return kwargs for snowflake.connector.connect()."""
    return {
        "account":   os.environ["SNOWFLAKE_ACCOUNT"],
        "user":      os.environ["SNOWFLAKE_USER"],
        "password":  os.environ["SNOWFLAKE_PASSWORD"],
        "warehouse": os.environ["SNOWFLAKE_WAREHOUSE"],
        "database":  os.environ["SNOWFLAKE_DATABASE"],
        "role":      os.environ.get("SNOWFLAKE_ROLE") or None,
    }


RAW_SCHEMA = os.environ.get("SNOWFLAKE_RAW_SCHEMA", "RAW")
RAW_TABLE = "PRICES"
