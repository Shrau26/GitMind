"""Enrich a sample of repos from the converted health/category datasets with
fields the Kaggle metadata dump doesn't include: closed issue count,
contributor count, and release count/recency.

The Kaggle dataset (pelmers/github-repository-metadata-with-5-stars) has
stars, forks, open issues, pushedAt, and pull requests — enough for a first
pass. It does NOT have closed issues, contributor count, or release history,
which your health.py heuristic also weighs (contributors: 10%, releases: 8%).
This script fills those in via the live GitHub API for a sample of repos, so
you can build a richer/more accurate health_dataset.csv.

Uses this machine's configured GITHUB_TOKEN (reads it from the environment —
never printed, never logged, never sent anywhere but api.github.com).

Usage:
    export GITHUB_TOKEN=...        # already configured on your machine
    python3 scripts/enrich_with_github_api.py datasets/health_dataset.csv \
        --limit 500 --out datasets/health_dataset_enriched.csv

Rate limits: authenticated GitHub API access is 5,000 requests/hour. Each
repo costs ~3 requests (contributors, releases, closed issues search), so
--limit 500 uses ~1,500 requests — safe for one run. Re-run later for more.
"""

import argparse
import csv
import os
import sys
import time
from pathlib import Path

import httpx

GITHUB_API_BASE = "https://api.github.com"


def _headers():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print("No GITHUB_TOKEN (or GH_TOKEN) found in this environment.")
        print("Set it the same way you already have it configured for GitMind itself, e.g.:")
        print("  export GITHUB_TOKEN=your_token_here")
        sys.exit(1)
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


def _get(client: httpx.Client, url: str, params: dict = None):
    resp = client.get(url, params=params)
    if resp.status_code == 403 and resp.headers.get("X-RateLimit-Remaining") == "0":
        reset = int(resp.headers.get("X-RateLimit-Reset", time.time() + 60))
        wait = max(1, reset - int(time.time()))
        print(f"Rate limited. Sleeping {wait}s...")
        time.sleep(wait)
        resp = client.get(url, params=params)
    return resp


def enrich_repo(client: httpx.Client, owner: str, repo: str) -> dict:
    out = {"closed_issues": None, "contributor_count": None, "release_count": None}

    # Closed issues via search API (cheap: 1 call, gives total_count without pagination)
    r = _get(client, f"{GITHUB_API_BASE}/search/issues",
             params={"q": f"repo:{owner}/{repo} type:issue state:closed", "per_page": 1})
    if r.status_code == 200:
        out["closed_issues"] = r.json().get("total_count")

    # Contributor count (approximate via Link header on page 1, per_page=1)
    r = _get(client, f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contributors",
             params={"per_page": 1, "anon": "true"})
    if r.status_code == 200:
        link = r.headers.get("Link", "")
        if 'rel="last"' in link:
            try:
                last_page = link.split('page=')[-1].split('&')[0].split('>')[0]
                out["contributor_count"] = int(last_page)
            except (ValueError, IndexError):
                out["contributor_count"] = len(r.json())
        else:
            out["contributor_count"] = len(r.json())

    # Release count (approximate via Link header, per_page=1)
    r = _get(client, f"{GITHUB_API_BASE}/repos/{owner}/{repo}/releases",
             params={"per_page": 1})
    if r.status_code == 200:
        link = r.headers.get("Link", "")
        if 'rel="last"' in link:
            try:
                last_page = link.split('page=')[-1].split('&')[0].split('>')[0]
                out["release_count"] = int(last_page)
            except (ValueError, IndexError):
                out["release_count"] = len(r.json())
        else:
            out["release_count"] = len(r.json())

    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input_csv", help="health_dataset.csv (must have an 'owner/repo' or 'name_with_owner' column — see note below)")
    parser.add_argument("--repo-col", default="name_with_owner",
                        help="Column containing 'owner/repo' (default: name_with_owner)")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    in_path = Path(args.input_csv)
    if not in_path.exists():
        print(f"File not found: {in_path}")
        sys.exit(1)

    out_path = Path(args.out) if args.out else in_path.with_name(in_path.stem + "_enriched.csv")

    with open(in_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("Input CSV is empty.")
        sys.exit(1)

    if args.repo_col not in rows[0]:
        print(f"Column '{args.repo_col}' not found. Available columns: {list(rows[0].keys())}")
        print("Tip: the pelmers Kaggle dataset has a 'nameWithOwner' field — keep it when you "
              "adapt convert_kaggle_dataset.py, so this script has something to look up.")
        sys.exit(1)

    rows = rows[: args.limit]
    headers = _headers()

    with httpx.Client(headers=headers, timeout=30.0) as client:
        for i, row in enumerate(rows, 1):
            owner_repo = row[args.repo_col]
            if "/" not in owner_repo:
                continue
            owner, repo = owner_repo.split("/", 1)
            print(f"[{i}/{len(rows)}] {owner_repo}")
            row.update(enrich_repo(client, owner, repo))

    fieldnames = list(rows[0].keys())
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {out_path} ({len(rows)} rows enriched with closed_issues, contributor_count, release_count)")


if __name__ == "__main__":
    main()
