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
- `public/data/*.json` + `public/data/manifest.json` — slimmed per-day PR data published for the site
- `public/index.html` — the interactive dashboard (copied from `templates/index.html`)

Serve the `public/` directory statically (GitHub Pages, Vercel, Cloudflare Pages, or `python -m http.server`);
the dashboard fetches the day files client-side, so opening `index.html` directly via `file://` won't work.
The page supports 1D / 7D / 30D / 1Y / All presets and a custom date range, aggregating stats across the
selected days in the browser.

## How it works

1. **`scripts/fetch_github.py`** — for a given local date and IANA timezone, computes the UTC window for that
   local day, runs a GitHub GraphQL `search` query (`is:pr is:merged merged:<utc-range>`) against both repos,
   paginates through all matches, and re-validates each PR's `mergedAt` against the exact local-day window in
   code (GitHub's search date filter is not always precise to the second). Each PR is tagged with an inferred
   `category` (keyword rules over title/body/labels) and a `highImpact` flag (large diffs, or keywords like
   "default", "cuda graph", "disaggregation", etc). Results are cached to `data/<date>.json`.
2. **`scripts/render_dashboard.py`** — publishes site data: strips heavy fields (`bodyExcerpt`, `labels`) from
   each cached day file into `public/data/`, writes a `manifest.json` date index, and copies
   `templates/index.html` to `public/index.html`. All stats aggregation happens client-side in the browser.
3. **`scripts/build_daily.py`** — runs both steps in sequence.

## CLI reference

```bash
python scripts/fetch_github.py --date YYYY-MM-DD [--timezone America/Los_Angeles] [--force]
python scripts/render_dashboard.py
python scripts/build_daily.py --date YYYY-MM-DD [--timezone America/Los_Angeles] [--force]
```

## Daily automation

`.github/workflows/daily-dashboard.yml` runs on a schedule (15:00 UTC ≈ 7-8 AM Pacific), fetches yesterday's
(Pacific time) merged PRs, republishes the site data, commits the generated files back to the repo, and deploys
`public/` to GitHub Pages.

## Copyright / attribution

This tool stores only normalized metadata and a 300-character body excerpt per PR — never full PR bodies or
diffs — and every PR links back to its GitHub page.

## Later upgrades (not in this MVP)

- Weekly trend page, module-level classification from changed file paths
- LLM-generated summaries, maintainer/reviewer activity
- Open PR backlog, roadmap issue progress
- vLLM vs SGLang feature battlecards (MoE, scheduler, KV cache, disaggregation, quantization, multimodal, structured output)
- RSS/email daily digest
