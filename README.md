# LLM Serving Development Tracker

Daily merged PR comparison between [sgl-project/sglang](https://github.com/sgl-project/sglang) and
[vllm-project/vllm](https://github.com/vllm-project/vllm), built from the GitHub GraphQL API (no HTML scraping).

## Quick start

```bash
pip install -r requirements.txt
export GITHUB_TOKEN=$(gh auth token)   # or a PAT with public_repo read access

python scripts/build_daily.py --date 2026-07-02 --timezone America/Los_Angeles
```

This writes:

- `data/2026-07-02.json` — normalized, cached PR data (raw fetch is skipped on rerun unless `--force` is passed)
- `public/reports/2026-07-02.html` — the archived report for that day
- `public/index.html` — a copy of the latest report

Open `public/index.html` in a browser, or serve the `public/` directory statically (GitHub Pages, Vercel, Cloudflare Pages, etc).

## How it works

1. **`scripts/fetch_github.py`** — for a given local date and IANA timezone, computes the UTC window for that
   local day, runs a GitHub GraphQL `search` query (`is:pr is:merged merged:<utc-range>`) against both repos,
   paginates through all matches, and re-validates each PR's `mergedAt` against the exact local-day window in
   code (GitHub's search date filter is not always precise to the second). Each PR is tagged with an inferred
   `category` (keyword rules over title/body/labels) and a `highImpact` flag (large diffs, or keywords like
   "default", "cuda graph", "disaggregation", etc). Results are cached to `data/<date>.json`.
2. **`scripts/render_dashboard.py`** — loads the cached JSON, computes per-repo summary stats (PR counts, author
   counts, category distribution, largest PR, high-impact PRs), generates cross-project insight bullets, and
   renders `templates/dashboard.html.j2` to a static HTML file.
3. **`scripts/build_daily.py`** — runs both steps in sequence.

## CLI reference

```bash
python scripts/fetch_github.py --date YYYY-MM-DD [--timezone America/Los_Angeles] [--force]
python scripts/render_dashboard.py --date YYYY-MM-DD
python scripts/build_daily.py --date YYYY-MM-DD [--timezone America/Los_Angeles] [--force]
```

## Daily automation

`.github/workflows/daily.yml` runs on a schedule (~6 AM America/Chicago), builds yesterday's report using the
repo's local timezone, and commits the generated `data/*.json` and `public/*.html` back to the repo.

## Copyright / attribution

This tool stores only normalized metadata and a 300-character body excerpt per PR — never full PR bodies or
diffs — and every PR links back to its GitHub page.

## Later upgrades (not in this MVP)

- Weekly trend page, module-level classification from changed file paths
- LLM-generated summaries, maintainer/reviewer activity
- Open PR backlog, roadmap issue progress
- vLLM vs SGLang feature battlecards (MoE, scheduler, KV cache, disaggregation, quantization, multimodal, structured output)
- RSS/email daily digest
