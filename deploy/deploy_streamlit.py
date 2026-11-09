"""Deploy the dashboard as a Streamlit in Snowflake app.

Uploads app/ (streamlit_app.py, data.py, environment.yml) to a stage and (re)creates
NYC_TLC.APPS.NYC_TLC_DASHBOARD. The same code runs locally and in Snowflake: data.py
switches to the app's built-in Snowpark session when hosted, so no credentials ship.

    python run.py deploy
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ingestion.load_to_snowflake import connect  # noqa: E402 — reuse the same auth logic

APP_FILES = ["streamlit_app.py", "data.py", "environment.yml"]
SCHEMA = "APPS"
STAGE = "STREAMLIT_STAGE"
APP = "NYC_TLC_DASHBOARD"
STAGE_DIR = "nyc_tlc_dashboard"

log = logging.getLogger("deploy")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("snowflake").setLevel(logging.WARNING)

    database = os.getenv("SNOWFLAKE_DATABASE", "NYC_TLC")
    warehouse = os.getenv("SNOWFLAKE_WAREHOUSE", "NYC_TLC_WH")
    fq_stage = f"{database}.{SCHEMA}.{STAGE}"
    fq_app = f"{database}.{SCHEMA}.{APP}"

    with connect() as conn, conn.cursor() as cur:
        cur.execute(f"create schema if not exists {database}.{SCHEMA} "
                    "comment = 'Applications built on the gold layer'")
        cur.execute(f"create stage if not exists {fq_stage} directory = (enable = true) "
                    "comment = 'Source files for Streamlit in Snowflake apps'")

        for name in APP_FILES:
            path = ROOT / "app" / name
            log.info("PUT %s", path.relative_to(ROOT).as_posix())
            cur.execute(f"put 'file://{path.as_posix()}' @{fq_stage}/{STAGE_DIR}/ "
                        "auto_compress = false overwrite = true")

        log.info("CREATE STREAMLIT %s", fq_app)
        cur.execute(f"""
            create or replace streamlit {fq_app}
                from '@{fq_stage}/{STAGE_DIR}/'
                main_file = 'streamlit_app.py'
                -- Warehouse runtime installs environment.yml from Snowflake's Anaconda
                -- channel. (The default container runtime needs a PyPI external access
                -- integration, which only ACCOUNTADMIN can create.)
                runtime_name = 'SYSTEM$WAREHOUSE_RUNTIME'
                query_warehouse = {warehouse}
                title = 'NYC Yellow Taxi Analytics'
                comment = 'Dashboard over NYC_TLC.GOLD (dbt). Deployed by run.py deploy.'
        """)
        # Apps created with FROM need a live version before they can be opened.
        try:
            cur.execute(f"alter streamlit {fq_app} add live version from last")
        except Exception as e:  # noqa: BLE001 — already live on some accounts
            log.info("live version: %s", str(e).splitlines()[0])

        org, account = cur.execute(
            "select current_organization_name(), current_account_name()").fetchone()
        log.info("Deployed. Open in Snowsight (role %s):", os.getenv("SNOWFLAKE_ROLE", "NYC_TLC_TRANSFORMER"))
        print(f"https://app.snowflake.com/{org.lower()}/{account.lower()}/#/streamlit-apps/{fq_app}")


if __name__ == "__main__":
    main()
