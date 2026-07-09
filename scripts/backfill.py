#!/usr/bin/env python3
"""Backfill PR data for a date range: fetch each missing day, then republish site data once."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"
DATA_DIR = ROOT / "data"


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def main():
    parser = argparse.ArgumentParser(description="Backfill merged-PR data over a date range")
    parser.add_argument("--from", dest="start", required=True, help="First date, YYYY-MM-DD (inclusive)")
    parser.add_argument("--to", dest="end", required=True, help="Last date, YYYY-MM-DD (inclusive)")
    parser.add_argument("--timezone", default="America/Los_Angeles", help="IANA timezone name for 'the day'")
    parser.add_argument("--force", action="store_true", help="Refetch days that already have cached data")
    parser.add_argument("--sleep", type=float, default=2.0, help="Seconds to pause between fetched days (rate-limit friendly)")
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    if start > end:
        print("ERROR: --from must be on or before --to", file=sys.stderr)
        sys.exit(1)

    failed = []
    fetched = skipped = 0
    for d in daterange(start, end):
        day = d.isoformat()
        if not args.force and (DATA_DIR / day[:4] / day[5:7] / f"{day}.json").exists():
            print(f"[skip] {day} (cached)")
            skipped += 1
            continue

        cmd = [sys.executable, str(SCRIPTS_DIR / "fetch_github.py"), "--date", day, "--timezone", args.timezone]
        if args.force:
            cmd.append("--force")
        print(f"[fetch] {day}")
        proc = subprocess.run(cmd)
        if proc.returncode != 0:
            print(f"[fail] {day} (exit {proc.returncode})", file=sys.stderr)
            failed.append(day)
        else:
            fetched += 1
        if args.sleep and d != end:
            time.sleep(args.sleep)

    print(f"\nDone: {fetched} fetched, {skipped} cached, {len(failed)} failed")
    if failed:
        print("Failed days: " + ", ".join(failed), file=sys.stderr)

    print("Republishing site data ...")
    subprocess.run([sys.executable, str(SCRIPTS_DIR / "render_dashboard.py")], check=True)

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
