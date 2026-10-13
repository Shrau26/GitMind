"""Convert the "GitHub Public Repository Metadata" Kaggle dataset
(pelmers/github-repository-metadata-with-5-stars) into GitMind's two
training CSVs: datasets/health_dataset.csv and datasets/category_dataset.csv.

Runs entirely locally, streams the input file rather than loading it into
memory (the raw dataset is ~500MB+), and never needs to be uploaded
anywhere — point it at the file you downloaded from Kaggle.

Usage:
    python3 scripts/convert_kaggle_dataset.py path/to/downloaded_file \
        [--sample-size 6000] [--per-category-cap 400]

Accepts .json (a JSON array of objects, streamed via ijson), .jsonl
(newline-delimited JSON), .csv, or a .zip containing one of those (reads
the first matching entry inside the zip without extracting it to disk).

Two important honesty notes, since this dataset doesn't come pre-labeled
for GitMind's schema:

1. `label` (healthy/fair/at_risk/critical) is auto-derived by running
   GitMind's own rule-based heuristic (health.py) over each row's stats.
   That means the trained classifier is learning to *approximate the
   existing heuristic* from raw stats, not learning some independent
   ground truth — useful as a starting point and to sanity-check that ML
   training works end-to-end, but it will never be more "correct" than
   the heuristic it was bootstrapped from. If you want a model that adds
   real signal beyond the heuristic, you'll eventually want to hand-label
   at least some rows yourself.

2. `category` is derived from each repo's `topics`/`description` via a
   fixed keyword map (see CATEGORY_KEYWORDS below) — also a heuristic
   bootstrap, not verified ground truth. Adjust CATEGORY_KEYWORDS to match
   the taxonomy you actually want, or hand-correct a sample afterward.
"""

import argparse
import csv
import io
import json
import random
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from health import compute_health, health_label  # noqa: E402

CATEGORY_KEYWORDS = {
    "web-framework": ["web-framework", "webframework", "express", "django", "flask",
                      "fastapi", "spring-boot", "rails", "laravel", "nestjs", "asp-net", "web-app"],
    "cli-tool": ["cli", "command-line", "commandline", "terminal", "shell-script", "cli-app", "cli-tool"],
    "ml-library": ["machine-learning", "deep-learning", "neural-network", "pytorch",
                   "tensorflow", "scikit-learn", "nlp", "computer-vision", "llm",
                   "artificial-intelligence", "ml-library", "generative-ai"],
    "frontend-library": ["react", "vue", "angular", "svelte", "frontend", "front-end",
                         "ui-library", "component-library", "css-framework", "design-system"],
    "backend": ["backend", "back-end", "server", "api-server", "rest-api", "graphql-server",
               "microservice", "backend-framework"],
    "database": ["database", "db", "sql", "nosql", "orm", "database-engine", "key-value-store",
                "postgres", "mysql", "mongodb", "redis", "sqlite"],
    "devops": ["devops", "kubernetes", "docker", "infrastructure", "terraform",
              "ci-cd", "cloud", "deployment", "sre", "iac", "helm", "ansible"],
    "mobile": ["android", "ios", "flutter", "react-native", "mobile-app", "swiftui", "kotlin-android", "mobile"],
    "security": ["security", "cybersecurity", "encryption", "penetration-testing", "vulnerability",
                "authentication", "cryptography", "infosec", "pentest"],
    "data-science": ["data-analysis", "data-engineering", "etl", "data-pipeline",
                     "data-visualization", "pandas", "spark", "data-science", "jupyter", "statistics"],
}

REQUIRED_ANY = ["stars", "forks", "issues", "pushedAt"]


def _days_since(iso_date):
    if not iso_date:
        return None
    try:
        dt = datetime.fromisoformat(str(iso_date).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return (datetime.now(timezone.utc) - dt).days


def _categorize(text: str):
    text_lower = (text or "").lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return category
    return None


def _iter_records(path: Path):
    """Yield dicts from .json / .jsonl / .csv, or the first matching entry in a .zip."""
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as zf:
            inner_name = next(
                (n for n in zf.namelist() if n.endswith((".json", ".jsonl", ".csv"))), None
            )
            if inner_name is None:
                print("No .json/.jsonl/.csv file found inside the zip.")
                sys.exit(1)
            print(f"Reading {inner_name} from inside the zip…")
            with zf.open(inner_name) as raw:
                yield from _iter_stream(raw, Path(inner_name).suffix)
        return

    with open(path, "rb") as raw:
        yield from _iter_stream(raw, path.suffix)


def _iter_stream(raw_binary_stream, suffix: str):
    if suffix == ".json":
        try:
            import ijson
        except ImportError:
            print("This dataset is a large JSON array and needs the 'ijson' package to "
                  "stream it without loading 500MB+ into memory.\n"
                  "Install it with: pip install ijson --break-system-packages")
            sys.exit(1)
        for obj in ijson.items(raw_binary_stream, "item"):
            yield obj
    elif suffix == ".jsonl":
        text_stream = io.TextIOWrapper(raw_binary_stream, encoding="utf-8")
        for line in text_stream:
            line = line.strip()
            if line:
                yield json.loads(line)
    elif suffix == ".csv":
        text_stream = io.TextIOWrapper(raw_binary_stream, encoding="utf-8", errors="replace")
        yield from csv.DictReader(text_stream)
    else:
        print(f"Unrecognized file type: {suffix}. Expected .json, .jsonl, .csv, or .zip.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input_path", help="Path to the downloaded Kaggle dataset file")
    parser.add_argument("--sample-size", type=int, default=6000,
                        help="Max rows to keep for the health dataset (default 6000)")
    parser.add_argument("--per-category-cap", type=int, default=400,
                        help="Max rows per category for the category dataset (default 400)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    input_path = Path(args.input_path).expanduser()
    if not input_path.exists():
        print(f"File not found: {input_path}")
        sys.exit(1)

    random.seed(args.seed)

    out_dir = Path(__file__).resolve().parent.parent / "datasets"
    out_dir.mkdir(parents=True, exist_ok=True)
    health_out = out_dir / "health_dataset.csv"
    category_out = out_dir / "category_dataset.csv"

    health_rows = []          # reservoir-sampled
    category_counts = {c: 0 for c in CATEGORY_KEYWORDS}
    category_rows = []

    seen = 0
    kept_health = 0
    kept_category = 0

    print(f"Streaming {input_path}…")
    for record in _iter_records(input_path):
        seen += 1
        if seen % 200000 == 0:
            print(f"  processed {seen:,} rows so far…")

        stars = record.get("stars")
        forks = record.get("forks")
        issues = record.get("issues")
        pushed_at = record.get("pushedAt") or record.get("pushed_at")
        pull_requests = record.get("pullRequests") or record.get("pull_requests") or 0
        description = record.get("description") or ""
        topics = record.get("topics")
        name_with_owner = record.get("nameWithOwner") or (
            f"{record.get('owner', '')}/{record.get('name', '')}".strip("/") or None
        )

        if stars is None or forks is None or issues is None or pushed_at is None:
            continue
        try:
            stars, forks, issues = int(stars), int(forks), int(issues)
            pull_requests = int(pull_requests) if pull_requests else 0
        except (ValueError, TypeError):
            continue

        # --- Health dataset row (reservoir sampling so this works on files
        # far larger than args.sample_size without buffering everything) ---
        days_since = _days_since(pushed_at)
        if days_since is not None:
            # Reuse the exact same heuristic the running app uses (health.py),
            # so the auto-derived label is consistent with what GitMind
            # would show for this repo today, then bucket it into the same
            # four labels via health_label().
            score, _flags, _breakdown = compute_health(
                stars=stars,
                open_issues=issues,
                last_commit_at=pushed_at,
                stale_pr_count=0,
                open_pr_count=pull_requests,
            )
            label = health_label(score).replace(" ", "_")  # "at risk" -> "at_risk"

            row = {
                "stars": stars,
                "forks": forks,
                "open_issues": issues,
                "days_since_last_commit": days_since,
                "stale_pr_count": 0,
                "open_pr_count": pull_requests,
                "label": label,
                "name_with_owner": name_with_owner,  # kept for enrich_with_github_api.py; drop before training if you prefer
            }
            kept_health += 1
            if len(health_rows) < args.sample_size:
                health_rows.append(row)
            else:
                j = random.randint(0, kept_health - 1)
                if j < args.sample_size:
                    health_rows[j] = row

        # --- Category dataset row ---
        topic_text = ""
        if isinstance(topics, list):
            topic_text = " ".join(
                t.get("name", "") if isinstance(t, dict) else str(t) for t in topics
            )
        elif isinstance(topics, str):
            topic_text = topics

        combined_text = f"{description} {topic_text}".strip()
        category = _categorize(combined_text)
        if category and category_counts[category] < args.per_category_cap and combined_text:
            category_counts[category] += 1
            kept_category += 1
            category_rows.append({"text": combined_text, "category": category})

    print(f"\nScanned {seen:,} total rows.")
    print(f"Health dataset: kept {len(health_rows)} rows (reservoir-sampled from {kept_health} eligible).")
    print(f"Category dataset: kept {kept_category} rows across {sum(1 for c in category_counts.values() if c > 0)} categories.")
    for cat, count in category_counts.items():
        print(f"  {cat}: {count}")

    with open(health_out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "stars", "forks", "open_issues", "days_since_last_commit",
            "stale_pr_count", "open_pr_count", "label", "name_with_owner",
        ])
        writer.writeheader()
        writer.writerows(health_rows)
    print(f"\nWrote {health_out}")

    with open(category_out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["text", "category"])
        writer.writeheader()
        writer.writerows(category_rows)
    print(f"Wrote {category_out}")

    print("\nNext step:")
    print("  cd backend")
    print("  python3 train_health_classifier.py datasets/health_dataset.csv")
    print("  python3 train_category_classifier.py datasets/category_dataset.csv")


if __name__ == "__main__":
    main()
