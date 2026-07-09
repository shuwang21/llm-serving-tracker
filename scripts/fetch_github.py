#!/usr/bin/env python3
"""Fetch merged PRs for sglang and vllm from the GitHub GraphQL API for a given local day."""

from __future__ import annotations

import argparse
import json
import os
import sys
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

SECRET_RE = re.compile(r"(ghp_|gho_|ghs_|ghu_|github_pat_|sk-|AKIA)[A-Za-z0-9_\-]{16,}")

REPOS = {
    "sglang": "sgl-project/sglang",
    "vllm": "vllm-project/vllm",
}

GRAPHQL_URL = "https://api.github.com/graphql"

SEARCH_QUERY = """
query($searchQuery: String!, $after: String) {
  search(query: $searchQuery, type: ISSUE, first: 50, after: $after) {
    issueCount
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on PullRequest {
        number
        title
        url
        author { login }
        mergedAt
        createdAt
        changedFiles
        additions
        deletions
        commits { totalCount }
        labels(first: 20) { nodes { name } }
        bodyText
        baseRefName
      }
    }
  }
}
"""

# Category rules, checked in order; first match wins.
CATEGORY_RULES = [
    ("AMD / ROCm", ["amd", "rocm", "hip", "mi300", "mi355", "aiter"]),
    ("NVIDIA / CUDA", ["cuda", "triton", "flashinfer", "flashmla", "blackwell", "b200", "h100", "h200", "gb300", "sm90", "sm120"]),
    ("Speculative Decoding", ["spec", "speculative", "eagle", "draft", "rejection sampler"]),
    ("MoE / Expert Parallel", ["moe", "expert", "ep", "eplb", "deepgemm", "fusedmoe"]),
    ("Scheduler / Runtime", ["scheduler", "runtime", "runner", "engine", "model runner"]),
    ("KV Cache / Memory", ["kv", "cache", "radix", "prefix cache", "pagedattention", "hicache", "memory"]),
    ("Distributed / PD Disaggregation", ["disagg", "prefill", "decode", "pd", "mooncake", "nixl", "rdma"]),
    ("Model Support", ["model", "llava", "glm", "qwen", "whisper", "mamba", "deepseek", "minimax", "grok"]),
    ("Frontend / API / Tool Calling", ["frontend", "rust frontend", "api", "openai", "tool parser", "tool call"]),
    ("Docs / Cookbook", ["doc", "docs", "cookbook", "readme"]),
    ("CI / Tests", ["ci", "test", "benchmark", "nightly"]),
    ("Cleanup / Refactor", ["cleanup", "refactor", "dead-code", "remove"]),
]

HIGH_IMPACT_KEYWORDS = [
    "default", "enable by default", "delete", "remove", "scheduler", "model runner",
    "cuda graph", "pagedattention", "disaggregation", "moe", "spec decode", "rocm",
    "deepgemm", "cache",
]

HIGH_IMPACT_LABELS = {"performance", "bug", "feature", "rocm", "cuda", "model"}


def classify(title: str, body: str, labels: list[str]) -> str:
    haystack = " ".join([title or "", body or ""] + labels).lower()
    for category, keywords in CATEGORY_RULES:
        for kw in keywords:
            if kw in haystack:
                return category
    return "Other"


def is_high_impact(pr: dict) -> bool:
    if pr["changedFiles"] >= 10:
        return True
    if pr["additions"] + pr["deletions"] >= 500:
        return True
    haystack = (pr["title"] + " " + pr["bodyExcerpt"]).lower()
    if any(kw in haystack for kw in HIGH_IMPACT_KEYWORDS):
        return True
    labels_lower = {l.lower() for l in pr["labels"]}
    if labels_lower & HIGH_IMPACT_LABELS:
        return True
    return False


def local_day_utc_window(date_str: str, tz_name: str):
    tz = ZoneInfo(tz_name)
    year, month, day = (int(p) for p in date_str.split("-"))
    local_start = datetime(year, month, day, 0, 0, 0, tzinfo=tz)
    local_end = local_start + timedelta(days=1)
    return local_start.astimezone(ZoneInfo("UTC")), local_end.astimezone(ZoneInfo("UTC"))


def graphql_request(token: str, query: str, variables: dict) -> dict:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "llm-serving-dev-tracker",
    }
    for attempt in range(5):
        try:
            resp = requests.post(
                GRAPHQL_URL,
                json={"query": query, "variables": variables},
                headers=headers,
                timeout=30,
            )
        except requests.RequestException:
            if attempt < 4:
                time.sleep(2 ** attempt)
                continue
            raise
        if resp.status_code in (502, 503, 504) and attempt < 4:
            time.sleep(2 ** attempt)
            continue
        if resp.status_code != 200:
            raise RuntimeError(f"GitHub API error {resp.status_code}: {resp.text}")
        body = resp.json()
        if "errors" in body:
            raise RuntimeError(f"GraphQL errors: {body['errors']}")
        return body["data"]
    raise RuntimeError("GraphQL request failed after retries")


def fetch_repo_prs(token: str, repo_slug: str, utc_start: datetime, utc_end: datetime) -> list[dict]:
    start_iso = utc_start.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    end_iso = utc_end.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    search_query = f"repo:{repo_slug} is:pr is:merged merged:{start_iso}..{end_iso}"

    prs = []
    after = None
    while True:
        data = graphql_request(token, SEARCH_QUERY, {"searchQuery": search_query, "after": after})
        search = data["search"]
        for node in search["nodes"]:
            if not node:
                continue
            prs.append(node)
        if not search["pageInfo"]["hasNextPage"]:
            break
        after = search["pageInfo"]["endCursor"]
    return prs


def normalize_pr(raw: dict, repo_key: str, utc_start: datetime, utc_end: datetime) -> dict | None:
    merged_at_str = raw.get("mergedAt")
    if not merged_at_str:
        return None
    merged_at = datetime.fromisoformat(merged_at_str.replace("Z", "+00:00"))
    # Re-validate against the exact local-day window; the search API's date
    # filtering can be imprecise, so this is the authoritative check.
    if not (utc_start <= merged_at < utc_end):
        return None

    body_text = (raw.get("bodyText") or "").strip()
    # Redact secret-looking strings (leaked tokens in PR bodies trip GitHub push protection)
    body_excerpt = SECRET_RE.sub(r"\1[REDACTED]", body_text[:300])
    labels = [n["name"] for n in raw.get("labels", {}).get("nodes", [])]
    author = raw.get("author")

    pr = {
        "repo": repo_key,
        "number": raw["number"],
        "title": raw["title"],
        "url": raw["url"],
        "author": author["login"] if author else "ghost",
        "mergedAt": merged_at_str,
        "createdAt": raw.get("createdAt"),
        "changedFiles": raw.get("changedFiles", 0),
        "additions": raw.get("additions", 0),
        "deletions": raw.get("deletions", 0),
        "commits": raw.get("commits", {}).get("totalCount", 0),
        "labels": labels,
        "baseRefName": raw.get("baseRefName"),
        "bodyExcerpt": body_excerpt,
    }
    pr["category"] = classify(pr["title"], body_text, labels)
    pr["highImpact"] = is_high_impact(pr)
    return pr


def main():
    parser = argparse.ArgumentParser(description="Fetch merged PRs for sglang/vllm on a given local day")
    parser.add_argument("--date", required=True, help="Local date, YYYY-MM-DD")
    parser.add_argument("--timezone", default="America/Los_Angeles", help="IANA timezone name for 'the day'")
    parser.add_argument("--force", action="store_true", help="Refetch even if cached data exists")
    parser.add_argument("--out-dir", default=str(Path(__file__).resolve().parent.parent / "data"))
    args = parser.parse_args()

    out_path = Path(args.out_dir) / f"{args.date}.json"
    if out_path.exists() and not args.force:
        print(f"Cache hit: {out_path} already exists (use --force to refetch)")
        return

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("ERROR: GITHUB_TOKEN environment variable is required", file=sys.stderr)
        sys.exit(1)

    utc_start, utc_end = local_day_utc_window(args.date, args.timezone)
    print(f"Local day {args.date} ({args.timezone}) => UTC [{utc_start.isoformat()}, {utc_end.isoformat()})")

    result = {
        "date": args.date,
        "timezone": args.timezone,
        "utc_start": utc_start.isoformat(),
        "utc_end": utc_end.isoformat(),
        "generated_at": datetime.now(ZoneInfo("UTC")).isoformat(),
        "repos": {},
    }

    for repo_key, repo_slug in REPOS.items():
        print(f"Fetching {repo_slug} ...")
        raw_prs = fetch_repo_prs(token, repo_slug, utc_start, utc_end)
        normalized = []
        for raw in raw_prs:
            pr = normalize_pr(raw, repo_key, utc_start, utc_end)
            if pr:
                normalized.append(pr)
        normalized.sort(key=lambda p: p["mergedAt"])
        result["repos"][repo_key] = normalized
        print(f"  {len(normalized)} merged PRs in window (raw search returned {len(raw_prs)})")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
