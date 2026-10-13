# GitMind

A GitHub repository analyzer. Paste a repository URL, GitMind fetches its
stats from the GitHub API (name, description, stars, forks, language, open
issues, commit recency, pull-request staleness), computes a health score and
risk flags, generates a plain-English summary from the README, and saves it
all to a local SQLite database.

**Stack:** React (Vite, plain JavaScript, React Router) + FastAPI (Python) +
SQLite. No Docker, no Postgres, no Redis, no auth, no external AI API.

```
GitMind/
├── backend/
│   ├── main.py            FastAPI app and REST endpoints
│   ├── database.py        SQLite connection + schema (with migrations)
│   ├── models.py          Pydantic request/response models
│   ├── github_client.py   GitHub URL parsing + API client (repo, commits, PRs, README)
│   ├── health.py          Heuristic 0–100 health score + risk flags
│   ├── summarizer.py      Local extractive README summarizer (no external API)
│   ├── ml/
│   │   ├── similarity.py           Similar-repo recommendations (TF-IDF, no dataset needed)
│   │   ├── anomaly.py              Outlier detection (Isolation Forest, no dataset needed)
│   │   ├── health_classifier.py    Learned health classifier (loads model if trained)
│   │   └── category_classifier.py  Learned category classifier (loads model if trained)
│   ├── train_health_classifier.py    Trains ml/health_classifier.py's model
│   ├── train_category_classifier.py  Trains ml/category_classifier.py's model
│   ├── datasets/           ~3,000-row real GitHub training CSVs (one per model) + format docs
│   ├── scripts/            collect_github_datasets.py rebuilds the CSVs from live GitHub data
│   ├── models/             Trained .joblib files land here (gitignored)
│   ├── requirements.txt
│   └── (no database file here — see "Your data lives outside the project folder" below)
└── frontend/
    ├── src/
    │   ├── App.jsx              route container + shell
    │   ├── ThemeContext.jsx     dark/light mode toggle (persisted)
    │   ├── api.js                fetch() wrappers for the backend
    │   ├── components/
    │   │   ├── NavBar.jsx        page nav + theme toggle
    │   │   ├── RepoCard.jsx      repo summary card (used on Home)
    │   │   └── HealthBadge.jsx   health score pill
    │   └── pages/
    │       ├── Home.jsx          analyze form + saved repo grid
    │       ├── RepoDetail.jsx    full detail: health, flags, summary, similar repos, ML predictions
    │       └── Dashboard.jsx     portfolio rollup, outlier detection, ML training status
    ├── index.html
    ├── package.json
    └── vite.config.js      proxies /api → http://localhost:8000
```

## Run it locally

You need Python 3.9+ and Node.js 18+.

### 1. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Optional: to enable **Ask GitMind / Gemini AI Advisor**, copy `backend/.env.example` to
`backend/.env` and add a `GEMINI_API_KEY`. Everything else works without it.

The API is now running at `http://localhost:8000`. Interactive docs are at
`http://localhost:8000/docs`.

**Your data lives outside the project folder, at `~/.gitmind/gitmind.db`**
(same idea on Windows: your user profile folder, e.g.
`C:\Users\you\.gitmind\gitmind.db`) — not inside `backend/`. This is
deliberate: if you replace the project folder with an updated copy later (a
new zip, a fresh `git clone`, etc.), your previously analyzed repos are
still there, because the code and your data are no longer stored in the
same place. The startup log prints the exact path being used, e.g.
`[GitMind] Using database: /home/you/.gitmind/gitmind.db`.

If you're upgrading from an older version of GitMind that stored
`gitmind.db` directly inside `backend/`, and you run this version *from
that same project folder*, your existing database is moved to the new
location automatically on first startup — nothing to do manually, and nothing
is deleted (the old `backend/gitmind.db` copy is left in place, just unused
from then on). This only works if you're updating the same folder in
place; if you already extracted a new copy to a different folder before
reading this, your old `backend/gitmind.db` is still sitting in the old
folder — copy it to `~/.gitmind/gitmind.db` yourself to recover it (see
below).

Want it somewhere else entirely — a specific data drive, a synced folder,
back to the old in-project behavior? Set the `GITMIND_DB_PATH` environment
variable before starting the backend:
```bash
export GITMIND_DB_PATH=/path/to/your/gitmind.db   # macOS/Linux
set GITMIND_DB_PATH=C:\path\to\gitmind.db          # Windows
```

To manually recover an old database from a previous project folder, stop
the backend and copy it into place:
```bash
mkdir -p ~/.gitmind
cp /path/to/old/project/backend/gitmind.db ~/.gitmind/gitmind.db
```

### 2. Frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The dev server proxies any request to `/api`
through to the FastAPI backend on port 8000.

## Using it

1. Paste a GitHub repository URL (e.g. `https://github.com/fastapi/fastapi`).
   `owner/repo` shorthand and `.git` URLs also work.
2. Optionally add a GitHub personal access token — this raises your GitHub API
   rate limit from 60 to 5,000 requests/hour and is required for private
   repositories. The token is only sent with that request; it is never stored.
3. Click **Analyze**. GitMind fetches the repo's stats, last commit date, open
   PR staleness, and README from GitHub, computes a health score, and stores
   everything in SQLite. Re-analyzing the same repo updates its saved record.
4. Click a repo's name (or open `/repo/:id`) to see its full detail page:
   health score, risk flags, and plain-English summary.
5. Visit **Dashboard** (`/dashboard`) for a portfolio rollup: average health
   score, a health-score distribution, and the riskiest repos you're tracking.
6. Toggle dark/light mode from the sun/moon button in the nav bar; the choice
   is remembered across reloads.

## Health score & risk flags

`backend/health.py` computes a 0–100 heuristic score per repo, deducting
points for:

- **Open-issue-to-star ratio** — flags "elevated"/"high open-issue ratio"
- **Commit recency** — flags "slowing activity" / "no recent activity" if the
  last commit is >90 / >365 days old
- **Stale pull requests** — flags "some"/"many stale pull requests" for PRs
  open more than 30 days

Each penalty scales continuously between a "starts to matter" threshold and
a "maxed out" threshold, rather than jumping in one fixed step — a project
with a 16% open-issue ratio and one with a 39% ratio both used to land on
the same "elevated" -15 penalty and the same final score; now they're
differentiated (e.g. 99 vs. 76) even though both still show the same flag
label. This is intentionally a transparent, hand-tuned heuristic rather than
a trained model: with only a handful of numeric signals and no labeled
"healthy vs. unhealthy" dataset, a weighted rule set is more accurate and
far more auditable than a model fit on nothing. All thresholds live at the
top of `health.py` if you want to retune them.

## Plain-English summary (no external AI API)

`backend/summarizer.py` generates a 2–3 sentence summary of each repo by
running frequency-weighted extractive summarization (a lightweight relative
of the classic Luhn/TextRank algorithms) over the README: it strips markdown
noise (badges, code fences, headers, tables), scores each remaining sentence
by how many high-frequency non-stopword terms it contains, and keeps the
top-scoring sentences in their original order.

This runs entirely locally — no API key, no network call beyond GitHub
itself, no training step. It's genuinely useful for surfacing a README's own
best "what is this" sentence, especially on jargon-heavy or sparse READMEs,
but it's extractive (it picks existing sentences) rather than generative, so
it won't rephrase or simplify jargon the way an LLM would. A real learned
summarization model needs a labeled dataset (README → ideal summary pairs)
and training infrastructure that's out of scope for a project this size — if
you have such a dataset, `summarizer.py` is a drop-in module you can swap out
without touching the rest of the app.

## Ask GitMind — Gemini AI Advisor

`POST /api/repos/{id}/ask` uses Google's Gemini API only as a concise explanation
layer. GitMind first classifies the question (`security`, `health`, `testing`,
`dependency`, `predictive`, or `general`) and sends only the relevant structured
evidence — never the whole repository or raw repository files.

The backend defaults to `gemini-2.5-flash-lite` and supports `GEMINI_MODEL` as an
environment override. Requests have a timeout, bounded input/output, API-key
validation, graceful provider-error fallback, and a small in-memory cache for
identical question/evidence combinations. `GEMINI_API_KEY` is backend-only and
is never placed in React code or logs.

Gemini does not calculate GitMind health scores or forecasts. Those remain
deterministic GitMind calculations; Gemini explains their supplied evidence.
If Gemini is unavailable, the API returns: **"AI Advisor temporarily
unavailable. GitMind analysis is still available."**

## Predictive Repository Risk

The **Repository Failure Forecast & Recovery Engine** is a deterministic
extension of the existing health/history/What-If systems.

- New endpoint: `GET /api/repos/{id}/predictive-risk`
- Historical snapshots now optionally carry a compact `metrics_json` payload;
  all existing snapshot columns remain intact.
- The engine compares real snapshots, derives observed trends, and reports
  current state, future direction, qualitative risk, confidence, evidence,
  associated risk pathways, and simulated interventions.
- It never invents missing history. With insufficient structural history it
  explicitly reports: **"Forecast requires additional repository history."**
- **Health Paradox** is raised only when an observed adjacent snapshot shows
  health increasing while at least two structural-risk indicators worsen.
- Intervention candidates are generated only for detected problems and reuse
  the existing weighted health-factor What-If logic. Efficiency is
  `simulated health improvement / estimated effort`, with effort bands
  Low/Medium/High. Results are labeled simulated/estimated, not guaranteed.
- Relationships are described as associated risk pathways rather than proven
  causal relationships.

The UI is shown as **Predictive Repository Risk** on the repository detail
page and includes current health, future direction, paradox status, pathways,
recommended first action, alternatives, evidence, and confidence.


## REST API

| Method | Endpoint            | Description                                   |
|--------|----------------------|------------------------------------------------|
| POST   | `/api/repos`         | Body: `{ "url": "...", "token": "..." }` (token optional). Analyzes a GitHub repo and saves/updates it, including health score, summary, branches, and contributors. |
| GET    | `/api/repos`         | List all saved repositories — favorites first, then most recently updated. |
| GET    | `/api/repos/{id}`    | Get a single saved repository by id.          |
| POST   | `/api/repos/{id}/refresh` | Body: `{ "token": "..." }` (optional). Re-runs the full analysis against GitHub and records a new history snapshot + change digest. |
| POST   | `/api/repos/{id}/rescore` | Re-applies whichever trained ML models exist right now to an already-saved repo — no re-fetch. See "Using the trained models" below. |
| POST   | `/api/repos/{id}/favorite` | Toggles the repo's pinned/favorite flag.  |
| DELETE | `/api/repos/{id}`    | Remove a saved repository.                    |
| GET    | `/api/repos/{id}/history` | Time-series of health/security/star snapshots, each with a "what changed" digest. |
| GET    | `/api/repos/{id}/predictive-risk` | Deterministic failure forecast, Health Paradox detection, pathways, and intervention ranking. |
| GET    | `/api/repos/{id}/similar` | Similar repos by TF-IDF cosine similarity. |
| GET    | `/api/repos/{id}/badge.svg` | A shields.io-style embeddable SVG badge showing the current health score. No auth — meant to be linked from a repo's own README. |
| POST   | `/api/repos/{id}/ask` | Body: `{ "question": "..." }`. Gemini-backed, topic-scoped Ask GitMind advisor; optional. |
| GET    | `/api/anomalies`     | Outlier detection report across all saved repos. |
| GET    | `/api/ml-status`     | Which trained (dataset-dependent) models are currently active. |
| GET    | `/api/health`        | Health check.                                 |

### Error handling

The backend returns clear HTTP status codes and JSON error messages for:

- `400` — the URL couldn't be parsed into an owner/repo 
- `401` — invalid GitHub token
- `403` — GitHub API rate limit exceeded (add a token to raise the limit)
- `404` — repository doesn't exist or isn't accessible
- `502` — GitHub API unreachable

Secondary signals (last commit date, PR staleness, README, branches,
contributors) fail gracefully — if GitHub can't return one of them, the
analysis still succeeds with that field left blank rather than erroring out.

## Branches & contributors

Every repo's detail page shows:

- **Branches** — all branch names (via the GitHub Branches API), with the
  default branch highlighted.
- **Contributors** — top contributors by commit count (via the Contributors
  API, capped at 10), rendered as a horizontal bar chart on the repo detail
  page. Like every other secondary signal this is fetched unauthenticated
  unless you supply a token, so it can come back empty if you've hit GitHub's
  60-requests/hour anonymous rate limit — add a token on the analyze form to
  raise that to 5,000/hour.

## Dashboard visualizations

The Dashboard (`/dashboard`) renders real charts (via
[Recharts](https://recharts.org)), not just CSS bars:

- **Health distribution** — bar chart of how many saved repos fall into
  each health bucket.
- **Top repos by stars** — horizontal bar chart of your highest-starred
  repos.
- **Needs attention** — your lowest-health-score repos, linked out to their
  detail pages.
- **Outliers** — the Isolation Forest anomaly report (needs 5+ saved repos).

## Language composition & commit activity

Every repo's detail page also shows:

- **Language composition** — a donut chart of the repo's code by language.
  This comes straight from GitHub's own linguist-based detection
  (`GET /repos/{owner}/{repo}/languages`, byte counts per language).
- **Commit activity** — an area chart of weekly commit counts over the last
  52 weeks, from GitHub's own `stats/commit_activity` endpoint (note: GitHub
  computes these asynchronously — the very first request for a repo can
  return no data while GitHub caches it server-side; the backend waits
  briefly and retries once automatically, and if it's still not ready a
  second analysis a little later will typically have it).

Both charts render an explanatory note in place of the chart (not a
misleading blank chart) when there's no data yet, rather than silently
disappearing.

## AI / machine learning features

GitMind ships four ML-powered features, split into two groups:

### Working with zero setup (unsupervised, no dataset needed)

- **Similar repositories** (`backend/ml/similarity.py`) — TF-IDF + cosine
  similarity over each repo's summary/description/language, refit on every
  request from whatever's currently in your database. Shown on each repo's
  detail page.
- **Outlier detection** (`backend/ml/anomaly.py`) — an Isolation Forest
  trained fresh on your saved repos' numeric stats (stars, forks, issues,
  issue ratio, commit recency, stale PRs) each time you load the Dashboard.
  Needs at least 5 saved repos to produce meaningful output.

Both of these are genuinely trained models — they just train on your saved
repos as the "dataset," so there's nothing to set up.

### Trained and active out of the box

- **Learned health-score classifier** (`backend/ml/health_classifier.py`,
  trained via `backend/train_health_classifier.py`) — a RandomForest
  classifier predicting the same `healthy / fair / at_risk / critical`
  buckets as the rule-based heuristic, so you can compare a learned model
  against the hand-tuned one.
- **Repo category classifier** (`backend/ml/category_classifier.py`,
  trained via `backend/train_category_classifier.py`) — a TF-IDF +
  logistic regression pipeline that tags a repo's domain (web framework,
  CLI tool, ML library, etc. — you define the taxonomy) from its README.

Both ship **pre-trained on ~3,000 real GitHub repositories each** (see
`backend/datasets/README.md` for exactly how the data is collected), so
`GET /api/ml-status` reports both as active and predictions show up
immediately. `backend/models/` contains `health_classifier.joblib` and
`category_classifier.joblib`.

Measured on held-out data (20% of each dataset, never seen in training):

| Model | Data | Held-out accuracy | 5-fold CV |
|-------|------|-------------------|-----------|
| Health classifier | 3,000 repos, 4 balanced classes | 99.0% | 99.0% (±0.4) |
| Category classifier | 3,000 repos, 10 categories x 300 | 75.8% | 75.9% (±1.2) |

**How to read those numbers honestly.** The health model's ~99% means it
reproduces the rule-based heuristic in `health.py` almost perfectly from raw
stats — its labels *are* that heuristic's output, so it can't be "more right"
than the heuristic (and pull-request counts aren't in the training data, so
that signal is ignored by the model). The category model is the one facing
real-world ambiguity: its labels come from repo authors' own GitHub topics,
which overlap heavily (a "web-framework" is often also "backend" or
"frontend-library"), and ~76% across 10 classes is a realistic result for
that, not a sign of a bug. Rebuild the data any time with
`python3 scripts/collect_github_datasets.py`.

### Retraining on your own data

Once you retrain, the model is used two ways:

1. **Automatically on every new analysis.** Any repo you analyze from now
   on gets scored by whichever models are currently
   active, alongside the rule-based heuristic.
2. **On demand, via the "Re-run AI predictions" button** on each repo's
   detail page (or `POST /api/repos/{id}/rescore` directly). This applies
   the current models to a repo you already saved *before* you retrained —
   no re-fetch from GitHub, it just re-scores
   the stats already stored in SQLite. Use this right after retraining to
   retroactively apply it across your saved repos without re-analyzing each
   one from scratch.

The **ML models** page in the sidebar (`/ml-status`) shows which of the two
trainable models are currently active, and gives the exact training
commands.

#### Dataset format

See `backend/datasets/README.md` and the `.example.csv` files there for the
exact column layout. Quick summary:

**Health dataset** — one row per repo, columns:
`stars, forks, open_issues, days_since_last_commit, stale_pr_count, open_pr_count, label`
where `label` is one of `healthy`, `fair`, `at_risk`, `critical`.
Aim for at least a few hundred rows per label; the shipped set has ~700–780.

**Category dataset** — one row per repo, columns: `text, category`, where
`text` is README content and/or description, and `category` is whatever
label taxonomy you choose. The shipped set has 300 per category.

#### Training

```bash
cd backend
python3 train_health_classifier.py datasets/your_dataset.csv
python3 train_category_classifier.py datasets/your_dataset.csv
```

Each script prints a held-out accuracy report before saving the model to
`backend/models/` (overwriting the shipped example model), so you can judge
whether it's actually good enough to trust before relying on it. Restart the
backend (`uvicorn main:app --reload` picks it up on its own reload) and the
new predictions activate.

**On "perfect accuracy":** no model is perfectly accurate, and any tool that
claims otherwise is being dishonest with you. The held-out report each
training script prints (accuracy + per-class precision/recall + 5-fold
cross-validation) is the real number for whatever data you train on.

## Notes

- SQLite storage means everything lives in a single `~/.gitmind/gitmind.db`
  file (see "Your data lives outside the project folder" above) — delete it
  to reset the app.
- Trained ML models live in `backend/models/` (gitignored) — delete a
  `.joblib` file there to deactivate that model without touching code.
- Still intentionally minimal: no authentication, no background jobs, no
  external infrastructure, no external AI/LLM API calls.
