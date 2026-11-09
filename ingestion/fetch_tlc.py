"""Download NYC TLC yellow-taxi monthly Parquet files into data/raw/.

TLC publishes one file per month, typically ~2 months after the month ends:
    https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_YYYY-MM.parquet

    python ingestion/fetch_tlc.py 2026-09            # one month
    python ingestion/fetch_tlc.py 2026-09 2026-10    # several
    python ingestion/fetch_tlc.py --check 2026-09    # only report whether it's published

Skips months already downloaded (use --overwrite to replace, e.g. when TLC republishes).
Downloads to a temporary file and validates the Parquet footer before keeping it, so a
failed or partial download never lands in data/raw/.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
BASE_URL = "https://d37ci6vzurychx.cloudfront.net/trip-data"
USER_AGENT = "nyc-tlc-analytics-pipeline/1.0"

log = logging.getLogger("fetch")


def month_arg(value: str) -> str:
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value):
        raise argparse.ArgumentTypeError(f"expected YYYY-MM, got {value!r}")
    return value


def url_for(month: str) -> str:
    return f"{BASE_URL}/yellow_tripdata_{month}.parquet"


def is_published(month: str) -> bool:
    req = urllib.request.Request(url_for(month), method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):  # the CDN answers 403 for files that don't exist yet
            return False
        raise


def fetch(month: str, overwrite: bool) -> Path | None:
    dest = RAW_DIR / f"yellow_tripdata_{month}.parquet"
    if dest.exists() and not overwrite:
        log.info("SKIP %s (already downloaded; --overwrite to replace)", dest.name)
        return dest
    if not is_published(month):
        log.warning("%s is not published yet (TLC releases each month ~2 months later)", dest.name)
        return None

    tmp = dest.with_suffix(".parquet.part")
    log.info("GET %s", url_for(month))
    req = urllib.request.Request(url_for(month), headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as out:
            while chunk := resp.read(1 << 20):
                out.write(chunk)
        with open(tmp, "rb") as f:  # Parquet files start and end with the magic bytes PAR1
            head = f.read(4)
            f.seek(-4, 2)
            tail = f.read(4)
        if head != b"PAR1" or tail != b"PAR1":
            raise ValueError(f"{tmp.name} is not a complete Parquet file")
        tmp.replace(dest)
    finally:
        tmp.unlink(missing_ok=True)
    log.info("SAVED %s (%.1f MB)", dest.relative_to(ROOT).as_posix(), dest.stat().st_size / 1e6)
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("months", nargs="+", type=month_arg, metavar="YYYY-MM")
    parser.add_argument("--overwrite", action="store_true", help="re-download months already in data/raw")
    parser.add_argument("--check", action="store_true", help="only report whether each month is published")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if args.check:
        for m in args.months:
            log.info("%s: %s", m, "published" if is_published(m) else "not published yet")
        return

    results = {m: fetch(m, args.overwrite) for m in args.months}
    if not all(results.values()):
        sys.exit(1)  # non-zero so a scheduler can retry later


if __name__ == "__main__":
    main()
