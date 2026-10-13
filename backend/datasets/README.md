# Datasets

GitMind's two trainable models are fit on **real GitHub data**, ~3,000 rows
each:

| File | Rows | Used by |
|------|------|---------|
| `health_dataset.csv`   | ~3,000 | `train_health_classifier.py` |
| `category_dataset.csv` | ~3,000 | `train_category_classifier.py` |

## Rebuilding / refreshing them

```bash
cd backend
export GITHUB_TOKEN=...            # optional, but makes collection much faster
python3 scripts/collect_github_datasets.py
python3 train_health_classifier.py   datasets/health_dataset.csv
python3 train_category_classifier.py datasets/category_dataset.csv
```

`collect_github_datasets.py` talks to GitHub's public search API (10
requests/minute without a token, so a full run takes ~20 minutes; with a token
it's a few minutes). Progress is cached in `datasets/.cache/`, so an
interrupted run resumes where it left off. Useful flags:
`--health-rows 3000`, `--per-category 300`, `--only health|category`.

### How each dataset is built

**Health dataset** (`stars, forks, open_issues, days_since_last_commit,
stale_pr_count, open_pr_count, label`)

* Real repositories sampled across a grid of star-count buckets x last-push
  windows (active this month ... untouched for 3+ years), so *all four*
  health classes are represented, not just popular, active projects.
  Extra sampling is aimed at the "moderately stale + lots of open issues"
  region, where the rare `at_risk` class lives.
* Every feature value is the repo's real number from GitHub.
* Classes are balanced (water-filled) so the model isn't dominated by the
  most common class.

**Category dataset** (`text, category`)

* Real repos discovered through their **author-assigned GitHub topics**
  (e.g. `topic:kubernetes` -> `devops`, `topic:pytorch` -> `ml-library`),
  10 categories, up to 300 repos each.
* The topics are used *only* to pick the label. The training text is the
  repo **description + the first part of its README** — the same kind of text
  the app feeds the model when you analyze a repo — so the model can't just
  read the answer out of the input.
* Repos matching topics from more than one category, and repos without a real
  description, are dropped as ambiguous.

## Things worth knowing before you trust the numbers

1. **Health labels are auto-derived, not human-verified.** The label is the
   verdict of GitMind's own rule-based heuristic (`health.py`) applied to the
   real stats. The classifier therefore learns to *approximate that
   heuristic* from raw numbers; a high score means it does that well, not
   that it has discovered an independent truth about repo health. For a
   model that adds new signal, hand-correct a sample of rows.
2. **Pull-request counts are not in this dataset.** GitHub's search API
   doesn't return per-repo PR counts, and fetching them for 3,000 repos
   would need thousands of extra authenticated calls, so `stale_pr_count`
   and `open_pr_count` are `0` in the training rows (the model simply learns
   to rely on the other five signals). When you analyze a real repo, the true
   PR numbers are still used by the rule-based score.
3. **`open_issues` from GitHub's search API includes open pull requests**
   (that's how GitHub defines `open_issues_count`).
4. **Category labels are topic-based**, so a repo tagged with topics from a
   single category is treated as belonging to it. That's a good proxy, not
   perfect ground truth.

## Alternative: the Kaggle dump

If you'd rather build from the big "GitHub Public Repository Metadata"
Kaggle dataset (https://www.kaggle.com/datasets/pelmers/github-repository-metadata-with-5-stars),
`scripts/convert_kaggle_dataset.py path/to/file.json` still works and writes
the same two CSVs (the same label caveats apply).

`health_dataset.example.csv` / `category_dataset.example.csv` are tiny
format references only.
