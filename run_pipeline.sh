#!/usr/bin/env bash
# Run the full pipeline: ingest prices, then build + test all dbt models.
set -euo pipefail
cd "$(dirname "$0")"

echo "==> [1/2] Ingesting prices from yfinance into Snowflake RAW.PRICES"
python ingestion/ingest.py

echo "==> [2/2] Building dbt models + tests"
set -a; . ./.env; set +a
export DBT_PROFILES_DIR="$(pwd)/dbt"
( cd dbt && dbt build )

echo "==> Done. Launch the dashboard with:  python dashboard/app.py"
