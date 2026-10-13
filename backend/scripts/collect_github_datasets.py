"""Build large, REAL training datasets straight from GitHub.

Produces (each ~2,000-3,000 rows by default):
    datasets/health_dataset.csv     -> train_health_classifier.py
    datasets/category_dataset.csv   -> train_category_classifier.py

Everything comes from live GitHub data:

* Health dataset - real repos sampled across star-count x last-push-date
  strata (so every health class is represented, not just popular/active
  repos). Features are the repo's real stars / forks / open issues / days
  since last push. The label is produced by GitMind's own rule-based
  heuristic (health.py), so the classifier learns the same four buckets the
  UI shows. NOTE: the inputs are real, but the label is the heuristic's
  verdict, not an independent human judgement - see datasets/README.md.

* Category dataset - real repos found via their *author-assigned GitHub
  topics* (e.g. topic:kubernetes -> devops). The topics are used ONLY to
  choose the label; the training text is the repo description + the start
  of its README (what the app actually sees at prediction time), so the model
  can't cheat by reading the label out of the text. Repos matching topics of
  more than one category are dropped as ambiguous.

Usage:
    export GITHUB_TOKEN=...          # optional but strongly recommended
    python3 scripts/collect_github_datasets.py [--health-rows 3000]
                                               [--per-category 300]

Without a token GitHub allows only 10 search requests/minute, so a full run
takes ~15-20 minutes; with a token it is a few minutes. Progress is cached in
datasets/.cache/ so an interrupted run resumes where it stopped.
"""

import argparse
import csv
import json
import math
import os
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from health import compute_health, health_label  # noqa: E402

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"
BACKEND = Path(__file__).resolve().parent.parent
DATASETS = BACKEND / "datasets"
CACHE = DATASETS / ".cache"

CATEGORY_TOPICS = {
    "web-framework": ["web-framework", "django", "flask", "fastapi", "expressjs", "rails", "laravel"],
    "cli-tool": ["cli", "command-line-tool", "cli-app", "terminal"],
    "ml-library": ["machine-learning", "deep-learning", "pytorch", "nlp", "computer-vision"],
    "frontend-library": ["react", "vue", "svelte", "ui-components", "css-framework"],
    "backend": ["backend", "rest-api", "microservices", "graphql-server"],
    "database": ["database", "sql", "orm", "redis", "mongodb"],
    "devops": ["devops", "kubernetes", "docker", "terraform", "ansible"],
    "mobile": ["android", "ios", "flutter", "react-native"],
    "security": ["security", "cryptography", "penetration-testing", "vulnerability-scanner"],
    "data-science": ["data-science", "data-visualization", "pandas", "jupyter-notebook", "etl"],
}

STAR_BUCKETS = ["10..30", "31..100", "101..300", "301..1000", "1001..3000", "3001..10000", "10001..60000"]


def _headers():
    h = {"Accept": "application/vnd.github+json", "User-Agent": "gitmind-dataset-builder"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


class Searcher:
    """Search API wrapper that respects GitHub's search rate limit."""

    def __init__(self):
        self.client = httpx.Client(headers=_headers(), timeout=30)
        self.delay = 2.2 if (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")) else 6.5
        self.calls = 0

    def repos(self, query: str, page: int = 1, sort: str = None):
        params = {"q": query, "per_page": 100, "page": page}
        if sort:
            params.update({"sort": sort, "order": "desc"})
        for attempt in range(6):
            time.sleep(self.delay)
            self.calls += 1
            try:
                r = self.client.get(f"{API}/search/repositories", params=params)
            except httpx.HTTPError:
                time.sleep(10)
                continue
            if r.status_code == 200:
                return r.json().get("items", [])
            if r.status_code in (403, 429):
                reset = int(r.headers.get("X-RateLimit-Reset", time.time() + 60))
                wait = min(90, max(5, reset - int(time.time()) + 1))
                print(f"  rate limited, sleeping {wait}s", flush=True)
                time.sleep(wait)
                continue
            if r.status_code == 422:
                return []
            time.sleep(5)
        return []


def slim(item: dict) -> dict:
    return {
        "full_name": item["full_name"],
        "stars": item["stargazers_count"],
        "forks": item["forks_count"],
        "open_issues": item["open_issues_count"],
        "pushed_at": item["pushed_at"],
        "archived": bool(item.get("archived")),
        "description": item.get("description") or "",
        "topics": item.get("topics") or [],
        "language": item.get("language") or "",
    }


def _load_cache(name):
    path = CACHE / name
    if path.exists():
        return json.loads(path.read_text())
    return {}


def _save_cache(name, obj):
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / name).write_text(json.dumps(obj))


def push_windows(today: datetime):
    d = lambda days: (today - timedelta(days=days)).strftime("%Y-%m-%d")
    return [
        f">={d(45)}",
        f"{d(120)}..{d(46)}",
        f"{d(270)}..{d(121)}",
        f"{d(540)}..{d(271)}",
        f"{d(1100)}..{d(541)}",
        f"<{d(1101)}",
    ]


def collect_health_pool(searcher: Searcher, want_rows: int):
    pool = _load_cache("health_pool.json")
    done = set(pool.get("_done", []))
    repos = pool.get("repos", {})
    windows = push_windows(datetime.now(timezone.utc))
    combos = [(s, w) for s in STAR_BUCKETS for w in windows]
    random.Random(7).shuffle(combos)
    pages = 2
    print(f"Health pool: {len(combos)} strata x {pages} page(s)", flush=True)
    for i, (stars, pushed) in enumerate(combos, 1):
        for page in range(1, pages + 1):
            key = f"{stars}|{pushed}|{page}"
            if key in done:
                continue
            items = searcher.repos(f"stars:{stars} pushed:{pushed} fork:false", page)
            for it in items:
                repos[it["full_name"]] = slim(it)
            done.add(key)
        _save_cache("health_pool.json", {"_done": sorted(done), "repos": repos})
        print(f"  [{i}/{len(combos)}] {stars} / {pushed}: pool={len(repos)}", flush=True)

    # The middle health classes ("fair" / "at risk") are naturally rare in a
    # uniform sample: a repo needs to be somewhat stale AND carry a high open-
    # issue load to land there. Oversample exactly that region (moderately
    # stale, many open help-wanted issues) so those classes get real examples.
    d = lambda days: (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    extra_windows = [f"{d(540)}..{d(200)}", f"{d(900)}..{d(541)}", f"{d(1500)}..{d(901)}"]
    for stars in ["10..30", "31..100", "101..300", "301..1000"]:
        for w in extra_windows:
            for page in (1, 2):
                key = f"x|{stars}|{w}|{page}"
                if key in done:
                    continue
                items = searcher.repos(f"stars:{stars} pushed:{w} help-wanted-issues:>2 fork:false", page)
                for it in items:
                    repos[it["full_name"]] = slim(it)
                done.add(key)
            _save_cache("health_pool.json", {"_done": sorted(done), "repos": repos})
            print(f"  [extra] {stars} / {w}: pool={len(repos)}", flush=True)
    return list(repos.values())


def collect_category_pool(searcher: Searcher, per_category: int):
    pool = _load_cache("category_pool.json")
    done = set(pool.get("_done", []))
    repos = pool.get("repos", {})  # full_name -> {"data":..., "cats": [..]}
    pages = 2
    jobs = [(cat, t, p) for cat, topics in CATEGORY_TOPICS.items() for t in topics for p in range(1, pages + 1)]
    print(f"Category pool: {len(jobs)} topic queries", flush=True)
    for i, (cat, topic, page) in enumerate(jobs, 1):
        key = f"{cat}|{topic}|{page}"
        if key in done:
            continue
        items = searcher.repos(f"topic:{topic} stars:>30 fork:false", page, sort="stars")
        for it in items:
            entry = repos.setdefault(it["full_name"], {"data": slim(it), "cats": []})
            if cat not in entry["cats"]:
                entry["cats"].append(cat)
        done.add(key)
        if i % 3 == 0 or i == len(jobs):
            _save_cache("category_pool.json", {"_done": sorted(done), "repos": repos})
            print(f"  [{i}/{len(jobs)}] {cat}/{topic}: pool={len(repos)}", flush=True)
    _save_cache("category_pool.json", {"_done": sorted(done), "repos": repos})
    return repos


def fetch_readme(full_name: str, client: httpx.Client) -> str:
    for fname in ("README.md", "readme.md", "README.rst", "README"):
        try:
            r = client.get(f"{RAW}/{full_name}/HEAD/{fname}")
        except httpx.HTTPError:
            continue
        if r.status_code == 200:
            return r.text[:6000]
    return ""


_CLEAN = [
    (re.compile(r"<[^>]+>"), " "),                 # html tags
    (re.compile(r"!\[[^\]]*\]\([^)]*\)"), " "),    # markdown images / badges
    (re.compile(r"\[([^\]]*)\]\([^)]*\)"), r"\1"),  # links -> text
    (re.compile(r"https?://\S+"), " "),
    (re.compile(r"[`*_>#|~=-]{1,}"), " "),
    (re.compile(r"\s+"), " "),
]


def clean_text(s: str) -> str:
    for pat, rep in _CLEAN:
        s = pat.sub(rep, s)
    return s.strip()


def build_health_csv(pool, target_rows: int, out_path: Path):
    rng = random.Random(42)
    now = datetime.now(timezone.utc)
    rows_by_label = {}
    for r in pool:
        try:
            pushed = datetime.fromisoformat(r["pushed_at"].replace("Z", "+00:00"))
        except (ValueError, TypeError, KeyError):
            continue
        days = max(0, (now - pushed).days)
        score, _flags, _breakdown = compute_health(
            stars=r["stars"], open_issues=r["open_issues"], last_commit_at=r["pushed_at"],
            stale_pr_count=0, open_pr_count=0,
        )
        label = health_label(score).lower().replace(" ", "_")
        rows_by_label.setdefault(label, []).append({
            "stars": r["stars"], "forks": r["forks"], "open_issues": r["open_issues"],
            "days_since_last_commit": days, "stale_pr_count": 0, "open_pr_count": 0,
            "label": label, "name_with_owner": r["full_name"],
        })
    print("Health pool label counts:", {k: len(v) for k, v in rows_by_label.items()}, flush=True)

    # water-filling allocation so rare classes keep everything they have
    labels = sorted(rows_by_label, key=lambda k: len(rows_by_label[k]))
    remaining, alloc = target_rows, {}
    for idx, lab in enumerate(labels):
        share = remaining // (len(labels) - idx)
        alloc[lab] = min(len(rows_by_label[lab]), share)
        remaining -= alloc[lab]

    final = []
    for lab, n in alloc.items():
        rng.shuffle(rows_by_label[lab])
        final.extend(rows_by_label[lab][:n])
    rng.shuffle(final)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(final[0].keys()))
        w.writeheader()
        w.writerows(final)
    print(f"Wrote {out_path} ({len(final)} rows): {alloc}", flush=True)


def build_category_csv(pool, per_category: int, out_path: Path):
    rng = random.Random(42)
    by_cat = {}
    for name, entry in pool.items():
        d = entry["data"]
        if len(entry["cats"]) != 1 or len(d["description"].strip()) < 20:
            continue  # ambiguous or nothing to learn from
        by_cat.setdefault(entry["cats"][0], []).append(d)
    picked = []
    for cat, items in by_cat.items():
        rng.shuffle(items)
        picked.extend((cat, d) for d in items[:per_category])
    print(f"Fetching READMEs for {len(picked)} repos…", flush=True)

    readme_cache = _load_cache("readmes.json")
    todo = [d["full_name"] for _, d in picked if d["full_name"] not in readme_cache]
    with httpx.Client(timeout=20, follow_redirects=True) as client, ThreadPoolExecutor(12) as ex:
        for i, (name, text) in enumerate(zip(todo, ex.map(lambda n: fetch_readme(n, client), todo)), 1):
            readme_cache[name] = text
            if i % 250 == 0:
                print(f"  readmes {i}/{len(todo)}", flush=True)
    _save_cache("readmes.json", readme_cache)

    rows = []
    for cat, d in picked:
        readme = clean_text(readme_cache.get(d["full_name"], ""))[:2500]
        text = " ".join(filter(None, [d["description"].strip(), readme]))
        rows.append({"text": text, "category": cat, "name_with_owner": d["full_name"]})
    rng.shuffle(rows)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["text", "category", "name_with_owner"])
        w.writeheader()
        w.writerows(rows)
    counts = {}
    for r in rows:
        counts[r["category"]] = counts.get(r["category"], 0) + 1
    with_readme = sum(1 for _, d in picked if readme_cache.get(d["full_name"]))
    print(f"Wrote {out_path} ({len(rows)} rows, {with_readme} with README): {counts}", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--health-rows", type=int, default=3000)
    ap.add_argument("--per-category", type=int, default=300)
    ap.add_argument("--only", choices=["health", "category"], default=None)
    args = ap.parse_args()

    DATASETS.mkdir(parents=True, exist_ok=True)
    searcher = Searcher()
    if args.only in (None, "health"):
        pool = collect_health_pool(searcher, args.health_rows)
        build_health_csv(pool, args.health_rows, DATASETS / "health_dataset.csv")
    if args.only in (None, "category"):
        cpool = collect_category_pool(searcher, args.per_category)
        build_category_csv(cpool, args.per_category, DATASETS / "category_dataset.csv")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
