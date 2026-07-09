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
HIGH_IMPACT_PER_MONTH = 100


def _impact_score(pr: dict) -> int:
    return pr["changedFiles"] + pr["additions"] + pr["deletions"]


def publish_site_data() -> None:
    """Publish slimmed per-day PR data, monthly pre-aggregated summaries, and a manifest."""
    site_data_dir = PUBLIC_DIR / "data"
    months_dir = site_data_dir / "months"
    months_dir.mkdir(parents=True, exist_ok=True)

    dates = []
    by_month: dict[str, list[dict]] = {}
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
        by_month.setdefault(data_path.stem[:7], []).append(data)

    for month, days in sorted(by_month.items()):
        summary = {"month": month, "days": [d["date"] for d in days], "repos": {}}
        repo_keys = {k for d in days for k in d["repos"]}
        for key in sorted(repo_keys):
            prs = [pr for d in days for pr in d["repos"].get(key, [])]
            authors: dict[str, int] = {}
            categories: dict[str, int] = {}
            additions = deletions = 0
            for pr in prs:
                authors[pr["author"]] = authors.get(pr["author"], 0) + 1
                categories[pr["category"]] = categories.get(pr["category"], 0) + 1
                additions += pr["additions"]
                deletions += pr["deletions"]
            high_impact = sorted(
                (pr for pr in prs if pr["highImpact"]), key=_impact_score, reverse=True
            )[:HIGH_IMPACT_PER_MONTH]
            summary["repos"][key] = {
                "total": len(prs),
                "additions": additions,
                "deletions": deletions,
                "authors": authors,
                "categories": categories,
                "highImpact": high_impact,
            }
        with open(months_dir / f"{month}.json", "w") as f:
            json.dump(summary, f, separators=(",", ":"))

    with open(site_data_dir / "manifest.json", "w") as f:
        json.dump({"dates": dates, "months": sorted(by_month)}, f)


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
