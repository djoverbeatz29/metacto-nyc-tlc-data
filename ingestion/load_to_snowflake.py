"""Load NYC TLC yellow-taxi Parquet files into Snowflake RAW (the landing zone).

Idempotent: Snowflake COPY INTO keeps 64 days of per-file load metadata, so re-running
skips files that are already loaded. Use --force to reload (rows for that file are
deleted first so a reload never duplicates).

    python ingestion/load_to_snowflake.py              # load every data/raw/yellow_tripdata_*.parquet
    python ingestion/load_to_snowflake.py --force      # reload them
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import snowflake.connector
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"

log = logging.getLogger("ingest")

# Explicit DDL (rather than INFER_SCHEMA) so the landing contract is stable across months:
# TLC has added columns over time (e.g. CBD_CONGESTION_FEE in 2025). With
# MATCH_BY_COLUMN_NAME, a file missing a column loads NULL instead of failing.
RAW_TABLE_DDL = """
create table if not exists raw.yellow_tripdata (
    vendorid               number,
    tpep_pickup_datetime   timestamp_ntz,
    tpep_dropoff_datetime  timestamp_ntz,
    passenger_count        number,
    trip_distance          float,
    ratecodeid             number,
    store_and_fwd_flag     varchar,
    pulocationid           number,
    dolocationid           number,
    payment_type           number,
    fare_amount            float,
    extra                  float,
    mta_tax                float,
    tip_amount             float,
    tolls_amount           float,
    improvement_surcharge  float,
    total_amount           float,
    congestion_surcharge   float,
    airport_fee            float,
    cbd_congestion_fee     float,
    request_source         varchar,
    -- load metadata
    _source_file           varchar,
    _source_row_number     number,
    _loaded_at             timestamp_ltz
)
comment = 'Landing table: NYC TLC yellow taxi trip records, loaded as-is from Parquet'
"""


def connect() -> snowflake.connector.SnowflakeConnection:
    load_dotenv(ROOT / ".env")
    missing = [k for k in ("SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER") if not os.getenv(k)]
    key_path = os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH")
    if not key_path and not os.getenv("SNOWFLAKE_PASSWORD"):
        missing.append("SNOWFLAKE_PRIVATE_KEY_PATH or SNOWFLAKE_PASSWORD")
    if missing:
        sys.exit(f"Missing {', '.join(missing)} — copy .env.example to .env and fill it in.")
    # Key-pair auth when a key is configured (no password stored anywhere); else password.
    auth = ({"private_key_file": os.path.expanduser(key_path)} if key_path
            else {"password": os.environ["SNOWFLAKE_PASSWORD"]})
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        role=os.getenv("SNOWFLAKE_ROLE", "NYC_TLC_TRANSFORMER"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "NYC_TLC_WH"),
        **auth,
    )


def run(cur, sql: str, *params):
    log.debug(sql.strip())
    cur.execute(sql, params or None)
    return cur.fetchall()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="reload files that were already loaded")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("snowflake").setLevel(logging.WARNING)  # connector logs every HTTP call at INFO

    files = sorted(RAW_DIR.glob("yellow_tripdata_*.parquet"))
    if not files:
        sys.exit(f"No yellow_tripdata_*.parquet files in {RAW_DIR}")

    database = os.getenv("SNOWFLAKE_DATABASE", "NYC_TLC")
    with connect() as conn, conn.cursor() as cur:
        run(cur, f"create database if not exists {database}")
        run(cur, f"use database {database}")
        run(cur, "create schema if not exists raw")
        run(cur, """
            create file format if not exists raw.parquet_ff
                type = parquet
                use_logical_type = true   -- read Parquet timestamps as timestamps, not epoch ints
        """)
        run(cur, "create stage if not exists raw.tlc_stage file_format = raw.parquet_ff")
        run(cur, RAW_TABLE_DDL)

        for f in files:
            log.info("PUT %s (%.1f MB)", f.name, f.stat().st_size / 1e6)
            # Forward slashes: Snowflake's PUT needs them even on Windows.
            run(cur, f"put 'file://{f.as_posix()}' @raw.tlc_stage/yellow/ auto_compress=false overwrite=true")
            if args.force:
                run(cur, "delete from raw.yellow_tripdata where _source_file = %s", f"yellow/{f.name}")

        log.info("COPY INTO raw.yellow_tripdata")
        results = run(cur, f"""
            copy into raw.yellow_tripdata
            from @raw.tlc_stage/yellow/
            pattern = '.*yellow_tripdata_.*[.]parquet'
            match_by_column_name = case_insensitive
            include_metadata = (
                _source_file = metadata$filename,
                _source_row_number = metadata$file_row_number,
                _loaded_at = metadata$start_scan_time
            )
            on_error = abort_statement
            {"force = true" if args.force else ""}
        """)
        for row in results:
            log.info("  %s", row)

        total = run(cur, "select _source_file, count(*) from raw.yellow_tripdata group by 1 order by 1")
        for source_file, n in total:
            log.info("raw.yellow_tripdata: %s -> %s rows", source_file, f"{n:,}")


if __name__ == "__main__":
    main()
