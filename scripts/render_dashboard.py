#!/usr/bin/env python3
"""Render the daily dashboard.html from a data/YYYY-MM-DD.json file produced by fetch_github.py."""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
from collections import Counter
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
TEMPLATES_DIR = ROOT / "templates"
PUBLIC_DIR = ROOT / "public"

REPO_LABELS = {"sglang": "SGLang", "vllm": "vLLM"}
REPO_URLS = {
    "sglang": "https://github.com/sgl-project/sglang",
    "vllm": "https://github.com/vllm-project/vllm",
}

CATEGORY_COLORS = {
    "AMD / ROCm": "#e0663f",
    "NVIDIA / CUDA": "#76b900",
    "Speculative Decoding": "#8b5cf6",
    "MoE / Expert Parallel": "#ec4899",
    "Scheduler / Runtime": "#0ea5e9",
    "KV Cache / Memory": "#f59e0b",
    "Distributed / PD Disaggregation": "#14b8a6",
    "Model Support": "#6366f1",
    "Frontend / API / Tool Calling": "#22c55e",
    "Docs / Cookbook": "#94a3b8",
    "CI / Tests": "#64748b",
    "Cleanup / Refactor": "#a8a29e",
    "Other": "#9ca3af",
}


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def compute_repo_stats(prs: list[dict]) -> dict:
    total = len(prs)
    author_counts = Counter(pr["author"] for pr in prs)
    category_counts = Counter(pr["category"] for pr in prs)
    total_additions = sum(pr["additions"] for pr in prs)
    total_deletions = sum(pr["deletions"] for pr in prs)
    largest_pr = max(prs, key=lambda p: p["changedFiles"], default=None)
    top_category = category_counts.most_common(1)[0] if category_counts else (None, 0)
    high_impact_prs = [p for p in prs if p["highImpact"]]

    return {
        "total": total,
        "unique_authors": len(author_counts),
        "total_additions": total_additions,
        "total_deletions": total_deletions,
        "top_authors": author_counts.most_common(10),
        "category_dist": category_counts.most_common(),
        "top_category": top_category,
        "largest_pr": largest_pr,
        "high_impact_prs": sorted(
            high_impact_prs, key=lambda p: p["changedFiles"] + p["additions"] + p["deletions"], reverse=True
        ),
    }


def _bold(text: str) -> str:
    return f"<strong>{html.escape(text)}</strong>"


def _link(text: str, url: str) -> str:
    return f'<a href="{html.escape(url)}" target="_blank" rel="noopener">{html.escape(text)}</a>'


def build_insights(stats: dict, prs: dict) -> list[Markup]:
    bullets = []
    s_stats, v_stats = stats["sglang"], stats["vllm"]

    if s_stats["total"] != v_stats["total"]:
        more, fewer = ("SGLang", "vLLM") if s_stats["total"] > v_stats["total"] else ("vLLM", "SGLang")
        more_n, fewer_n = (s_stats["total"], v_stats["total"]) if more == "SGLang" else (v_stats["total"], s_stats["total"])
        bullets.append(
            f"{_bold(more)} merged more PRs than {_bold(fewer)} ({more_n} vs {fewer_n})."
        )
    else:
        bullets.append(f"Both projects merged the same number of PRs ({s_stats['total']}).")

    def diversity_ratio(st):
        return st["unique_authors"] / st["total"] if st["total"] else 0

    s_div, v_div = diversity_ratio(s_stats), diversity_ratio(v_stats)
    if s_stats["total"] and v_stats["total"]:
        if abs(s_div - v_div) > 0.02:
            broader = "SGLang" if s_div > v_div else "vLLM"
            bullets.append(
                f"{_bold(broader)} had a broader author distribution "
                f"(SGLang: {s_stats['unique_authors']} authors / {s_stats['total']} PRs, "
                f"vLLM: {v_stats['unique_authors']} authors / {v_stats['total']} PRs)."
            )
        else:
            bullets.append("Author distribution was similarly broad in both projects.")

    if s_stats["top_category"][0]:
        bullets.append(
            f"SGLang's most active category was {_bold(s_stats['top_category'][0])} "
            f"({s_stats['top_category'][1]} PRs)."
        )
    if v_stats["top_category"][0]:
        bullets.append(
            f"vLLM's most active category was {_bold(v_stats['top_category'][0])} "
            f"({v_stats['top_category'][1]} PRs)."
        )

    combined_high_impact = (
        [dict(p, repo_label=REPO_LABELS["sglang"]) for p in prs["sglang"] if p["highImpact"]]
        + [dict(p, repo_label=REPO_LABELS["vllm"]) for p in prs["vllm"] if p["highImpact"]]
    )
    combined_high_impact.sort(key=lambda p: p["changedFiles"] + p["additions"] + p["deletions"], reverse=True)
    if combined_high_impact:
        top_n = combined_high_impact[:5]
        listing = "; ".join(
            _link(f"{p['repo_label']} #{p['number']} {p['title']}", p["url"]) for p in top_n
        )
        bullets.append(f"Notable potentially high-impact PRs today: {listing}.")
    else:
        bullets.append("No PRs matched the high-impact heuristics today.")

    return [Markup(b) for b in bullets]


def render(date: str, force_public: bool = True) -> Path:
    data_path = DATA_DIR / f"{date}.json"
    if not data_path.exists():
        raise FileNotFoundError(f"No data file at {data_path}; run fetch_github.py first")

    with open(data_path) as f:
        data = json.load(f)

    repos = data["repos"]
    stats = {repo_key: compute_repo_stats(prs) for repo_key, prs in repos.items()}
    insights = build_insights(stats, repos)

    # annotate PRs with a css-safe category slug for badge styling
    for repo_key, prs in repos.items():
        for pr in prs:
            pr["category_slug"] = slugify(pr["category"])

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    template = env.get_template("dashboard.html.j2")
    html = template.render(
        date=data["date"],
        timezone=data["timezone"],
        generated_at=data["generated_at"],
        repo_labels=REPO_LABELS,
        repo_urls=REPO_URLS,
        repos=repos,
        stats=stats,
        insights=insights,
        category_colors=CATEGORY_COLORS,
    )

    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    reports_dir = PUBLIC_DIR / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    report_path = reports_dir / f"{date}.html"
    with open(report_path, "w") as f:
        f.write(html)

    if force_public:
        shutil.copyfile(report_path, PUBLIC_DIR / "index.html")

    return report_path


def main():
    parser = argparse.ArgumentParser(description="Render the daily dashboard HTML from cached PR data")
    parser.add_argument("--date", required=True, help="Local date, YYYY-MM-DD (must match a data/<date>.json file)")
    args = parser.parse_args()

    report_path = render(args.date)
    print(f"Wrote {report_path}")
    print(f"Wrote {PUBLIC_DIR / 'index.html'}")


if __name__ == "__main__":
    main()
