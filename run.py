"""Cross-platform task runner. Loads .env, then runs the pipeline step(s).

    python run.py keygen    # one-time: create a Snowflake key pair + print the SQL to register it
    python run.py fetch 2026-09 [...]   # download TLC monthly file(s) into data/raw/
    python run.py load      # ingest new data/raw/*.parquet into Snowflake RAW (--force [--month M])
    python run.py update 2026-09        # fetch -> load -> build: add a new month end to end
    python run.py deps      # install dbt packages
    python run.py build     # dbt seed + run + test, layer by layer (bronze -> silver -> gold)
    python run.py docs      # generate and serve dbt docs (lineage graph) on :8080
    python run.py app       # launch the Streamlit dashboard locally
    python run.py deploy    # deploy the same dashboard as a Streamlit in Snowflake app
    python run.py all       # load -> deps -> build
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
DBT_DIR = ROOT / "dbt"
BIN = Path(sys.executable).parent  # the active venv's Scripts/ or bin/


def sh(*cmd: str, cwd: Path = ROOT) -> None:
    print(f"\n$ {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, cwd=cwd, env=os.environ)
    if result.returncode:
        sys.exit(result.returncode)


def dbt(*args: str) -> None:
    sh(str(BIN / "dbt"), *args, "--project-dir", str(DBT_DIR), "--profiles-dir", str(DBT_DIR), cwd=DBT_DIR)


def keygen() -> None:
    """Create an RSA key pair for Snowflake key-pair auth in ~/.snowflake (outside the repo)."""
    from cryptography.hazmat.primitives import serialization as s
    from cryptography.hazmat.primitives.asymmetric import rsa

    key_dir = Path.home() / ".snowflake"
    key_dir.mkdir(exist_ok=True)
    priv = key_dir / "nyc_tlc_rsa_key.p8"
    if priv.exists():
        sys.exit(f"{priv} already exists — not overwriting. Delete it first to rotate the key.")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv.write_bytes(key.private_bytes(s.Encoding.PEM, s.PrivateFormat.PKCS8, s.NoEncryption()))
    pub = key.public_key().public_bytes(s.Encoding.PEM, s.PublicFormat.SubjectPublicKeyInfo).decode()
    (key_dir / "nyc_tlc_rsa_key.pub").write_text(pub)
    body = "".join(line for line in pub.splitlines() if "-----" not in line)
    print(f"Private key: {priv}\nSet SNOWFLAKE_PRIVATE_KEY_PATH={priv.as_posix()} in .env\n")
    print("Run in a Snowsight worksheet:\n")
    print((ROOT / "setup" / "snowflake_keypair.sql").read_text().replace("<PASTE_PUBLIC_KEY_BODY_HERE>", body))


def fetch() -> None:
    sh(sys.executable, "ingestion/fetch_tlc.py", *sys.argv[2:])


def load() -> None:
    # `load` forwards its own flags; `update`/`all` pass months, which load doesn't take.
    extra = sys.argv[2:] if sys.argv[1] == "load" else []
    sh(sys.executable, "ingestion/load_to_snowflake.py", *extra)


def deps() -> None:
    dbt("deps")


def build() -> None:
    dbt("source", "freshness")
    # Layer-by-layer so a failing bronze test stops bad data before silver/gold are rebuilt.
    # "cautious" = only run tests whose parents are ALL in this layer; cross-layer
    # reconciliation tests run last, once every layer exists.
    for selector in ("tag:reference", "source:raw tag:bronze", "tag:silver", "tag:gold"):
        dbt("build", "--select", *selector.split(), "--indirect-selection", "cautious")
    dbt("test", "--select", "test_type:singular")


def docs() -> None:
    dbt("docs", "generate")
    dbt("docs", "serve", "--port", "8080")


def app() -> None:
    sh(sys.executable, "-m", "streamlit", "run", "app/streamlit_app.py")


def deploy() -> None:
    sh(sys.executable, "deploy/deploy_streamlit.py")


TASKS = {"keygen": [keygen], "fetch": [fetch], "update": [fetch, load, build], "load": [load], "deps": [deps], "build": [build], "docs": [docs], "app": [app],
         "deploy": [deploy], "all": [load, deps, build]}

if __name__ == "__main__":
    load_dotenv(ROOT / ".env")
    if len(sys.argv) < 2 or sys.argv[1] not in TASKS:
        sys.exit(__doc__)
    for task in TASKS[sys.argv[1]]:
        task()
