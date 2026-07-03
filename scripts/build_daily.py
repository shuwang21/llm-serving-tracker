#!/usr/bin/env python3
"""Single entrypoint: fetch merged PRs for a local day, then render the dashboard."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description="Fetch + render the daily vLLM vs SGLang PR dashboard")
    parser.add_argument("--date", required=True, help="Local date, YYYY-MM-DD")
    parser.add_argument("--timezone", default="America/Los_Angeles", help="IANA timezone name for 'the day'")
    parser.add_argument("--force", action="store_true", help="Refetch even if cached data exists")
    args = parser.parse_args()

    fetch_cmd = [
        sys.executable, str(SCRIPTS_DIR / "fetch_github.py"),
        "--date", args.date,
        "--timezone", args.timezone,
    ]
    if args.force:
        fetch_cmd.append("--force")
    subprocess.run(fetch_cmd, check=True)

    render_cmd = [sys.executable, str(SCRIPTS_DIR / "render_dashboard.py"), "--date", args.date]
    subprocess.run(render_cmd, check=True)


if __name__ == "__main__":
    main()
