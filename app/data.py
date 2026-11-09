"""Data access for the dashboard. Reads ONLY gold-layer models.

Gold marts are small pre-aggregated tables (hundreds to low thousands of rows), so each
one is pulled once, cached for an hour, and sliced in pandas. Filtering therefore costs
no warehouse compute, and every number on screen comes from a tested gold model.

Runs unchanged in two places:
  * Streamlit in Snowflake: uses the app's built-in Snowpark session (no credentials;
    queries run as the app owner role on the app's query warehouse).
  * Locally: connects with the key pair / password from the repo-root .env.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st


def _snowpark_session():
    """The active session when hosted in Snowflake, else None."""
    try:
        from snowflake.snowpark.context import get_active_session

        return get_active_session()
    except Exception:  # noqa: BLE001 — not installed, or no active session (local run)
        return None


SESSION = _snowpark_session()
IN_SNOWFLAKE = SESSION is not None

if not IN_SNOWFLAKE:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")

GOLD = f"{os.getenv('SNOWFLAKE_DATABASE', 'NYC_TLC')}.gold"


@st.cache_resource(show_spinner=False)
def _connection():
    import snowflake.connector

    key_path = os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH")
    auth = ({"private_key_file": os.path.expanduser(key_path)} if key_path
            else {"password": os.environ["SNOWFLAKE_PASSWORD"]})
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        **auth,
        role=os.getenv("SNOWFLAKE_ROLE", "NYC_TLC_TRANSFORMER"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "NYC_TLC_WH"),
        session_parameters={"QUERY_TAG": "nyc_tlc_streamlit"},
        client_session_keep_alive=True,
    )


@st.cache_data(ttl=3600, show_spinner="Loading from Snowflake gold layer…")
def _query(sql: str) -> pd.DataFrame:
    if IN_SNOWFLAKE:
        df = SESSION.sql(sql).to_pandas()
    else:
        with _connection().cursor() as cur:
            cur.execute(sql)
            df = cur.fetch_pandas_all()
    df.columns = [c.lower() for c in df.columns]
    # Snowflake NUMBER -> object/Decimal in some cases; make measures numeric.
    for c in df.columns:
        if df[c].dtype == object:
            try:
                df[c] = pd.to_numeric(df[c])
            except (ValueError, TypeError):
                pass  # genuinely text
    return df


def trip_volume_hourly() -> pd.DataFrame:
    df = _query(f"select * from {GOLD}.agg_trip_volume_hourly order by pickup_hour")
    df["pickup_hour"] = pd.to_datetime(df["pickup_hour"])
    df["pickup_date"] = pd.to_datetime(df["pickup_date"])
    df["pickup_week"] = pd.to_datetime(df["pickup_week"])
    return df


def zone_revenue_daily() -> pd.DataFrame:
    df = _query(f"select * from {GOLD}.agg_zone_revenue_daily")
    df["pickup_date"] = pd.to_datetime(df["pickup_date"])
    return df


def payment_behavior_daily() -> pd.DataFrame:
    df = _query(f"select * from {GOLD}.agg_payment_behavior_daily")
    df["pickup_date"] = pd.to_datetime(df["pickup_date"])
    return df


def data_quality() -> pd.DataFrame:
    df = _query(f"select * from {GOLD}.agg_data_quality order by source_month, rows_flagged desc")
    df["source_month"] = pd.to_datetime(df["source_month"])
    return df


def last_refreshed() -> pd.Timestamp | None:
    df = _query(
        f"select max(last_altered) as refreshed from {os.getenv('SNOWFLAKE_DATABASE', 'NYC_TLC')}"
        ".information_schema.tables where table_schema = 'GOLD'"
    )
    return df["refreshed"].iloc[0] if len(df) else None
