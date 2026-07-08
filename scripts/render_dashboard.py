#!/usr/bin/env python3
"""Publish site data for the interactive dashboard: slim per-day JSON files, a date manifest, and index.html."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
TEMPLATES_DIR = ROOT / "templates"
PUBLIC_DIR = ROOT / "public"

SLIM_PR_DROP_KEYS = {"bodyExcerpt", "labels"}


def publish_site_data() -> None:
    """Publish slimmed per-day PR data + a date manifest for the interactive index page."""
    site_data_dir = PUBLIC_DIR / "data"
    site_data_dir.mkdir(parents=True, exist_ok=True)

    dates = []
    for data_path in sorted(DATA_DIR.glob("????-??-??.json")):
        dates.append(data_path.stem)
        with open(data_path) as f:
            data = json.load(f)
        for prs in data["repos"].values():
            for pr in prs:
                for key in SLIM_PR_DROP_KEYS:
                    pr.pop(key, None)
        with open(site_data_dir / data_path.name, "w") as f:
            json.dump(data, f, separators=(",", ":"))

    with open(site_data_dir / "manifest.json", "w") as f:
        json.dump({"dates": dates}, f)


def main():
    parser = argparse.ArgumentParser(description="Publish site data + index.html from cached PR data")
    parser.add_argument("--date", help="Ignored (kept for build_daily.py compatibility)")
    parser.parse_args()

    publish_site_data()
    print(f"Wrote {PUBLIC_DIR / 'data'} (slim day files + manifest)")

    shutil.copyfile(TEMPLATES_DIR / "index.html", PUBLIC_DIR / "index.html")
    print(f"Wrote {PUBLIC_DIR / 'index.html'}")


if __name__ == "__main__":
    main()
