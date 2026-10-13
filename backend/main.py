"""GitMind API — a small FastAPI backend that analyzes GitHub repositories."""

import asyncio
import json
from datetime import datetime, timezone
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()  # reads backend/.env if present — must run before ai_advisor
                # (or anything else) reads os.environ for API keys.

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

import branch_analysis
import ci_cd
import contributor_analysis
import dependencies as deps
import documentation_analysis
import issues_analysis
import license_detection
import pr_analysis
import release_analysis
import repo_signals
import testing_analysis
import ai_advisor
from badge import render_health_badge
from changelog import build_digest
from predictive_risk import analyze_predictive_risk, build_current_metrics
from database import DB_PATH, get_connection, get_latest_snapshot, get_snapshots, init_db, record_snapshot
from github_client import (
    GitHubError,
    fetch_branch_activity,
    fetch_branch_total_count,
    fetch_branches,
    fetch_commit_activity,
    fetch_contributor_total_count,
    fetch_contributors,
    fetch_dependabot_alerts,
    fetch_file_content,
    fetch_issue_search_counts,
    fetch_languages,
    fetch_last_commit_date,
    fetch_open_issues_sample,
    fetch_open_prs,
    fetch_pr_merged_count,
    fetch_readme,
    fetch_recent_closed_prs,
    fetch_release_total_count,
    fetch_releases,
    fetch_repo_details,
    fetch_repo_tree,
    fetch_root_contents,
    fetch_workflow_runs,
    parse_github_url,
)
from health import compute_health, health_label
from ml import anomaly as anomaly_model
from ml import category_classifier
from ml import health_classifier
from ml import similarity as similarity_model
from models import (
    AnomalyReportResponse,
    AskRequest,
    RefreshRequest,
    RepoAnalyzeRequest,
    RepoResponse,
    SimilarRepoResponse,
)
from summarizer import summarize

app = FastAPI(
    title="GitMind API",
    description="A small tool that fetches and stores basic GitHub repository stats.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _days_since_iso(iso_date) -> None:
    if not iso_date:
        return None
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return (datetime.now(timezone.utc) - dt).days


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    print(f"[GitMind] Using database: {DB_PATH}")


@app.get("/")
def root():
    return {"message": "GitMind API is running", "docs": "/docs"}


CACHE_TTL_SECONDS = 1800  # reuse a recent analysis for 30 minutes unless the user explicitly refreshes

# One lock per repo (owner/repo, lowercased) so that if the same repo is
# requested twice at once — a double-click, two browser tabs, whatever —
# the second request waits for the first to finish and picks up its fresh
# result from cache instead of independently hitting GitHub's API a second
# time. This is purely in-process (not shared across multiple backend
# instances), which is the right scope for a single-user local tool.
_repo_locks: dict = {}


def _get_repo_lock(key: str) -> asyncio.Lock:
    lock = _repo_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _repo_locks[key] = lock
    return lock


def _cache_is_fresh(updated_at_str: Optional[str]) -> bool:
    if not updated_at_str:
        return False
    try:
        dt = datetime.strptime(updated_at_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return False
    return (datetime.now(timezone.utc) - dt).total_seconds() < CACHE_TTL_SECONDS


def _find_cached_github_repo(owner: str, repo: str):
    """Case-insensitive lookup — GitHub repo names are case-insensitive,
    so 'Owner/Repo' and 'owner/repo' should hit the same cache entry."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM repositories WHERE full_name = ? COLLATE NOCASE AND source = 'github'",
            (f"{owner}/{repo}",),
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


@app.get("/api/health")
def health_check():
    return {"status": "ok"}


@app.post("/api/repos", response_model=RepoResponse)
async def analyze_repo(payload: RepoAnalyzeRequest):
    """Parse a GitHub URL, fetch its details, and save/update it in SQLite.

    Serves a cached result (no GitHub API calls at all) when this repo was
    analyzed within the last CACHE_TTL_SECONDS, unless force_refresh is
    set — see the /refresh endpoint below, which always sets it."""
    try:
        owner, repo = parse_github_url(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    lock = _get_repo_lock(f"{owner}/{repo}".lower())
    async with lock:
        if not payload.force_refresh:
            cached = _find_cached_github_repo(owner, repo)
            if cached and _cache_is_fresh(cached["updated_at"]):
                cached["from_cache"] = True
                cached["cached_at"] = cached["updated_at"]
                return cached

        try:
            data = await fetch_repo_details(owner, repo, payload.token)
        except GitHubError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

        result = await _perform_github_analysis(owner, repo, data, payload.token)
        return result

async def _perform_github_analysis(owner: str, repo: str, data: dict, token) -> dict:
    """Runs the full GitHub analysis pipeline (all secondary API calls, scoring,
    and DB save) given the primary repo details already fetched. Shared by the
    initial analyze endpoint and the explicit refresh endpoint below."""
    # Secondary signals (commit recency, PRs, README, branches, contributors,
    # CI/CD runs, releases, root directory listing, Dependabot alerts, issue
    # counts, merged-PR count, contributor total) are best-effort: if any of
    # these calls fail, we degrade gracefully rather than failing the whole
    # analysis, since the core repo stats above already succeeded.
    (
        last_commit_at,
        open_prs,
        readme_text,
        branches,
        contributors_sample,
        languages,
        commit_activity,
        workflow_runs,
        releases,
        root_contents,
        dependabot_alerts,
        issue_counts,
        open_issues_sample,
        merged_pr_count,
        recent_closed_prs,
        contributor_total_count,
        release_total_count,
        branch_total_count,
        repo_tree,
    ) = await asyncio.gather(
        fetch_last_commit_date(owner, repo, token, data.get("default_branch")),
        fetch_open_prs(owner, repo, token),
        fetch_readme(owner, repo, token),
        fetch_branches(owner, repo, token),
        fetch_contributors(owner, repo, token, limit=25),
        fetch_languages(owner, repo, token),
        fetch_commit_activity(owner, repo, token),
        fetch_workflow_runs(owner, repo, token),
        fetch_releases(owner, repo, token),
        fetch_root_contents(owner, repo, token),
        fetch_dependabot_alerts(owner, repo, token),
        fetch_issue_search_counts(owner, repo, token),
        fetch_open_issues_sample(owner, repo, token),
        fetch_pr_merged_count(owner, repo, token),
        fetch_recent_closed_prs(owner, repo, token),
        fetch_contributor_total_count(owner, repo, token),
        fetch_release_total_count(owner, repo, token),
        fetch_branch_total_count(owner, repo, token),
        fetch_repo_tree(owner, repo, data.get("default_branch"), token),
    )

    # Branch activity needs the branch names from above first, so it's a
    # second, smaller round rather than the main gather.
    branch_activity = await fetch_branch_activity(owner, repo, branches, token, limit=8)

    # The existing "contributors" display field (Contributors bar chart) is
    # capped at the first 10, same as before — the larger 25-contributor
    # sample above is only used for the concentration analysis, which needs
    # a bigger sample to be meaningful.
    contributors = contributors_sample[:10]

    pr_stats = pr_analysis.summarize_prs(open_prs, merged_pr_count, recent_closed_prs)
    issue_stats = issues_analysis.summarize_issues(issue_counts, open_issues_sample)
    contributor_stats = contributor_analysis.summarize_contributors(contributors_sample, contributor_total_count)

    # health.py's scoring still wants a plain (open_pr_count, stale_pr_count)
    # pair — sourced from the same fetch as the richer pr_analysis summary
    # above rather than a second API call.
    open_pr_count = pr_stats["open_prs"]
    stale_pr_count = pr_stats["stale_prs"]

    # Root-level signals (tests, docs, dependency manifests) come from a
    # single directory listing; only the manifest files actually present get
    # a second, targeted fetch for their content.
    root_signals = repo_signals.detect_signals(
        (c["name"], c["type"]) for c in root_contents if c.get("name")
    )
    dependency_files_found = root_signals["dependency_files_found"]
    lock_files_found = root_signals["lock_files_found"]
    file_contents = {}
    if dependency_files_found:
        fetched = await asyncio.gather(
            *(fetch_file_content(owner, repo, fname, token) for fname in dependency_files_found)
        )
        file_contents = dict(zip(dependency_files_found, fetched))

    lock_file_contents = {}
    if lock_files_found:
        fetched_locks = await asyncio.gather(
            *(fetch_file_content(owner, repo, fname, token) for fname in lock_files_found)
        )
        lock_file_contents = dict(zip(lock_files_found, fetched_locks))

    dependency_report = deps.build_dependency_report(dependency_files_found, file_contents)
    security_summary = deps.summarize_security(dependabot_alerts)
    dependency_report["security"] = security_summary
    dependency_report = deps.enrich_dependency_report(
        dependency_report, lock_files_found, lock_file_contents, dependabot_alerts
    )

    ci_summary = ci_cd.summarize_ci(workflow_runs)

    doc_score = repo_signals.compute_doc_score(
        readme_text,
        root_signals["has_contributing"],
        root_signals["has_license"],
        root_signals["has_docs_dir"],
    )

    # Prefer the accurate total (Link-header trick) for the health score's
    # bus-factor signal; fall back to the sample size if that lookup failed.
    contributor_count = contributor_total_count if contributor_total_count is not None else (
        len(contributors_sample) if contributors_sample else None
    )

    release_count = len(releases)
    last_release_at = None
    if releases:
        dated = [r["published_at"] for r in releases if r.get("published_at")]
        if dated:
            last_release_at = max(dated)

    health_score, risk_flags, health_breakdown = compute_health(
        stars=data["stars"],
        open_issues=data["open_issues"],
        last_commit_at=last_commit_at,
        stale_pr_count=stale_pr_count,
        open_pr_count=open_pr_count,
        contributor_count=contributor_count,
        release_count=release_count,
        last_release_at=last_release_at,
        ci_summary=ci_summary,
        security_summary=security_summary,
        has_tests=root_signals["has_tests"],
        doc_score=doc_score,
    )
    health_status = health_label(health_score)

    release_stats = release_analysis.summarize_releases(releases, release_total_count)
    branch_stats = branch_analysis.summarize_branches(
        data.get("default_branch"), branch_activity, branch_total_count
    )
    testing_stats = testing_analysis.summarize_testing(
        repo_tree["paths"] if repo_tree["available"] else None,
        available=repo_tree["available"],
        reason=None if repo_tree["available"] else "Could not fetch the repo's file tree from GitHub.",
        truncated=repo_tree["truncated"],
    )
    documentation_stats = documentation_analysis.summarize_documentation(
        readme_text, has_contributing_file=root_signals["has_contributing"]
    )
    license_stats = license_detection.summarize_license_github(
        data.get("license_spdx_id"), data.get("license_name")
    )
    topics = data.get("topics") or []

    repo_summary = summarize(data["description"], readme_text, data["name"])

    # Learned health classifier: inactive (returns None) until a model is
    # trained via train_health_classifier.py — see README. The rule-based
    # health_score/risk_flags above always run regardless, so the app is
    # never blocked on training a model.
    ml_health_prediction = health_classifier.predict(
        stars=data["stars"],
        open_issues=data["open_issues"],
        forks=data["forks"],
        last_commit_at=last_commit_at,
        stale_pr_count=stale_pr_count,
        open_pr_count=open_pr_count,
    )
    ml_health_label = ml_health_prediction[0] if ml_health_prediction else None
    ml_health_confidence = ml_health_prediction[1] if ml_health_prediction else None

    # Learned category classifier: same story — inactive until trained via
    # train_category_classifier.py.
    category_text = " ".join(filter(None, [data["description"], readme_text]))
    category_prediction = category_classifier.predict(category_text)
    predicted_category = category_prediction[0] if category_prediction else None
    predicted_category_confidence = category_prediction[1] if category_prediction else None

    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO repositories
                (owner, name, full_name, description, stars, forks, open_issues, language, url,
                 last_commit_at, open_pr_count, stale_pr_count, health_score, risk_flags, summary,
                 predicted_category, predicted_category_confidence, ml_health_label, ml_health_confidence,
                 branches, contributors, languages, commit_activity, contributor_count,
                 health_status, health_breakdown, ci_cd, dependencies, releases,
                 issue_analysis, pr_analysis, contributor_analysis,
                 release_analysis, branch_analysis, testing_analysis,
                 documentation_analysis, license_info, topics, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(full_name) DO UPDATE SET
                description = excluded.description,
                stars = excluded.stars,
                forks = excluded.forks,
                open_issues = excluded.open_issues,
                language = excluded.language,
                url = excluded.url,
                last_commit_at = excluded.last_commit_at,
                open_pr_count = excluded.open_pr_count,
                stale_pr_count = excluded.stale_pr_count,
                health_score = excluded.health_score,
                risk_flags = excluded.risk_flags,
                summary = excluded.summary,
                predicted_category = excluded.predicted_category,
                predicted_category_confidence = excluded.predicted_category_confidence,
                ml_health_label = excluded.ml_health_label,
                ml_health_confidence = excluded.ml_health_confidence,
                branches = excluded.branches,
                contributors = excluded.contributors,
                languages = excluded.languages,
                commit_activity = excluded.commit_activity,
                contributor_count = excluded.contributor_count,
                health_status = excluded.health_status,
                health_breakdown = excluded.health_breakdown,
                ci_cd = excluded.ci_cd,
                dependencies = excluded.dependencies,
                releases = excluded.releases,
                issue_analysis = excluded.issue_analysis,
                pr_analysis = excluded.pr_analysis,
                contributor_analysis = excluded.contributor_analysis,
                release_analysis = excluded.release_analysis,
                branch_analysis = excluded.branch_analysis,
                testing_analysis = excluded.testing_analysis,
                documentation_analysis = excluded.documentation_analysis,
                license_info = excluded.license_info,
                topics = excluded.topics,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                data["owner"],
                data["name"],
                data["full_name"],
                data["description"],
                data["stars"],
                data["forks"],
                data["open_issues"],
                data["language"],
                data["url"],
                last_commit_at,
                open_pr_count,
                stale_pr_count,
                health_score,
                json.dumps(risk_flags),
                repo_summary,
                predicted_category,
                predicted_category_confidence,
                ml_health_label,
                ml_health_confidence,
                json.dumps(branches),
                json.dumps(contributors),
                json.dumps(languages),
                json.dumps(commit_activity),
                contributor_count,
                health_status,
                json.dumps(health_breakdown),
                json.dumps(ci_summary),
                json.dumps(dependency_report),
                json.dumps(releases),
                json.dumps(issue_stats),
                json.dumps(pr_stats),
                json.dumps(contributor_stats),
                json.dumps(release_stats),
                json.dumps(branch_stats),
                json.dumps(testing_stats),
                json.dumps(documentation_stats),
                json.dumps(license_stats),
                json.dumps(topics),
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM repositories WHERE full_name = ?", (data["full_name"],)
        ).fetchone()

        previous_snapshot = get_latest_snapshot(conn, row["id"])
        current_metrics = {
            "health_score": health_score,
            "security_score": security_summary.get("security_score"),
            "stars": data["stars"],
            "contributor_count": contributor_count,
            "open_issues": data["open_issues"],
            "open_pr_count": open_pr_count,
        }
        digest_text = build_digest(previous_snapshot, current_metrics)

        record_snapshot(
            conn,
            row["id"],
            health_score=health_score,
            security_score=security_summary.get("security_score"),
            days_since_last_commit=_days_since_iso(last_commit_at),
            open_issues=data["open_issues"],
            open_pr_count=open_pr_count,
            stars=data["stars"],
            contributor_count=contributor_count,
            digest=digest_text,
            metrics=build_current_metrics({
                "health_score": health_score,
                "health_breakdown": health_breakdown,
                "open_issues": data["open_issues"],
                "open_pr_count": open_pr_count,
                "stale_pr_count": stale_pr_count,
                "contributor_count": contributor_count,
                "contributor_analysis": contributor_stats,
                "pr_analysis": pr_stats,
                "testing_analysis": testing_stats,
                "dependencies": dependency_report,
                "ci_cd": ci_summary,
            }),
        )
        conn.commit()
    finally:
        conn.close()

    return dict(row)


@app.get("/api/repos", response_model=List[RepoResponse])
def list_repos():
    """Return all previously analyzed repositories — favorites first, then
    most recently updated."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM repositories ORDER BY is_favorite DESC, updated_at DESC"
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@app.get("/api/repos/{repo_id}", response_model=RepoResponse)
def get_repo(repo_id: int):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM repositories WHERE id = ?", (repo_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    return dict(row)


@app.get("/api/repos/{repo_id}/badge.svg")
def get_health_badge(repo_id: int):
    """A small embeddable SVG badge — "GitMind Health | 87" — colored to
    match the same health bucket used everywhere else in the app. Meant to
    be pointed at from a repo's own README, the same way a CI build-status
    badge works: ![GitMind Health](.../api/repos/{id}/badge.svg). No auth,
    since a badge only works publicly if anyone loading the README can
    fetch it — the health score itself isn't sensitive data."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT health_score FROM repositories WHERE id = ?", (repo_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    svg = render_health_badge(row["health_score"])
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-cache, max-age=0"},
    )


@app.get("/api/repos/{repo_id}/predictive-risk")
def get_predictive_risk(repo_id: int):
    """Deterministic Repository Failure Forecast & Recovery Engine."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM repositories WHERE id = ?", (repo_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Repository not found")
        repo = RepoResponse(**dict(row)).model_dump()
        snapshots = get_snapshots(conn, repo_id)
    finally:
        conn.close()
    return analyze_predictive_risk(repo, snapshots)


@app.post("/api/repos/{repo_id}/ask")
async def ask_about_repo(repo_id: int, payload: AskRequest):
    """Ask GitMind — answers a free-text question about this one repo,
    grounded entirely in data GitMind already computed for it (see
    ai_advisor.py). Gemini is optional; provider failures fall back without disabling GitMind analysis."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM repositories WHERE id = ?", (repo_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Repository not found")
        # Run the row through the same validated model the read endpoints use,
        # so ai_advisor gets real lists/dicts (risk_flags, dependencies, ...)
        # instead of the raw JSON-text columns SQLite actually stores.
        repo = RepoResponse(**dict(row)).model_dump()
        latest_snapshot = get_latest_snapshot(conn, repo_id)
    finally:
        conn.close()

    latest_digest = latest_snapshot["digest"] if latest_snapshot else None
    conn = get_connection()
    try:
        snapshots = get_snapshots(conn, repo_id)
    finally:
        conn.close()
    predictive = analyze_predictive_risk(repo, snapshots)

    try:
        answer = await ai_advisor.ask_about_repo(repo, payload.question, latest_digest, predictive)
        return {"answer": answer, "ai_available": True}
    except ai_advisor.AdvisorError as exc:
        # AI is an optional explanation layer. Never take down GitMind's
        # deterministic analysis when Gemini is unavailable, rate-limited, or
        # not configured. Invalid questions still return a normal validation error.
        if exc.code == "invalid_question":
            raise HTTPException(status_code=400, detail=exc.message) from exc
        return {
            "answer": "AI Advisor temporarily unavailable. GitMind analysis is still available.",
            "ai_available": False,
            "reason": exc.code,
        }


@app.post("/api/repos/{repo_id}/favorite", response_model=RepoResponse)
def toggle_favorite(repo_id: int):
    """Flip a repo's pinned/favorite flag. Toggles rather than taking an
    explicit on/off value — the frontend always just wants "the opposite of
    whatever it is now", and a toggle endpoint means the button never has to
    know the current state ahead of the click."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT is_favorite FROM repositories WHERE id = ?", (repo_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Repository not found")
        new_value = 0 if row["is_favorite"] else 1
        conn.execute(
            "UPDATE repositories SET is_favorite = ? WHERE id = ?", (new_value, repo_id)
        )
        conn.commit()
        updated = conn.execute("SELECT * FROM repositories WHERE id = ?", (repo_id,)).fetchone()
    finally:
        conn.close()
    return dict(updated)


@app.post("/api/repos/{repo_id}/rescore", response_model=RepoResponse)
def rescore_repo(repo_id: int):
    """Re-run the learned health and category classifiers against an
    already-saved repo, using its already-stored stats/summary — no GitHub
    API call, no re-fetch. This is the explicit "use the trained AI models"
    action: train a model with train_health_classifier.py /
    train_category_classifier.py, restart the backend, then call this
    endpoint (the "Re-run AI predictions" button in the UI) on any repo you
    analyzed before the model existed, to apply it retroactively."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM repositories WHERE id = ?", (repo_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Repository not found")
        repo = dict(row)

        ml_health_prediction = health_classifier.predict(
            stars=repo["stars"],
            open_issues=repo["open_issues"],
            forks=repo["forks"],
            last_commit_at=repo["last_commit_at"],
            stale_pr_count=repo["stale_pr_count"],
            open_pr_count=repo["open_pr_count"],
        )
        ml_health_label = ml_health_prediction[0] if ml_health_prediction else None
        ml_health_confidence = ml_health_prediction[1] if ml_health_prediction else None

        category_text = " ".join(filter(None, [repo.get("description"), repo.get("summary")]))
        category_prediction = category_classifier.predict(category_text)
        predicted_category = category_prediction[0] if category_prediction else None
        predicted_category_confidence = category_prediction[1] if category_prediction else None

        conn.execute(
            """
            UPDATE repositories SET
                ml_health_label = ?,
                ml_health_confidence = ?,
                predicted_category = ?,
                predicted_category_confidence = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (ml_health_label, ml_health_confidence, predicted_category, predicted_category_confidence, repo_id),
        )
        conn.commit()
        updated = conn.execute("SELECT * FROM repositories WHERE id = ?", (repo_id,)).fetchone()
    finally:
        conn.close()
    return dict(updated)


@app.delete("/api/repos/{repo_id}")
def delete_repo(repo_id: int):
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM repositories WHERE id = ?", (repo_id,)
        ).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Repository not found")
        conn.execute("DELETE FROM repositories WHERE id = ?", (repo_id,))
        conn.commit()
    finally:
        conn.close()
    return {"message": "Repository deleted"}


@app.get("/api/repos/{repo_id}/history")
def get_repo_history(repo_id: int):
    """Point-in-time snapshots of this repo's key metrics, one per real
    analysis (see record_snapshot() in database.py — nothing here is
    backfilled or estimated). Returns them oldest-first, ready for a line
    chart. Empty list (not a 404) if the repo has only ever been analyzed
    once — a single point isn't a trend, but it's not an error either."""
    conn = get_connection()
    try:
        repo = conn.execute("SELECT id FROM repositories WHERE id = ?", (repo_id,)).fetchone()
        if repo is None:
            raise HTTPException(status_code=404, detail="Repository not found")
        snapshots = get_snapshots(conn, repo_id)
    finally:
        conn.close()
    return snapshots


@app.post("/api/repos/{repo_id}/refresh", response_model=RepoResponse)
async def refresh_repo(repo_id: int, payload: RefreshRequest):
    """Force a fresh analysis of an already-saved repo — bypasses the
    cache entirely, records a new historical snapshot, and updates
    "last analyzed" (the repositories.updated_at column).

    Graceful failure: nothing is written to the database until the *entire*
    fetch succeeds (see _perform_github_analysis), so
    if the refresh fails partway — rate limit, network blip, repo went
    private — the repo's last successfully saved data is left completely
    untouched. The error is returned so the frontend can show it, but
    there's nothing to "roll back": the old data was never overwritten."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM repositories WHERE id = ?", (repo_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    row = dict(row)

    try:
        owner, repo = parse_github_url(row["full_name"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    lock = _get_repo_lock(f"{owner}/{repo}".lower())
    async with lock:
        try:
            data = await fetch_repo_details(owner, repo, payload.token)
        except GitHubError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
        return await _perform_github_analysis(owner, repo, data, payload.token)


@app.get("/api/repos/{repo_id}/similar", response_model=List[SimilarRepoResponse])
def get_similar_repos(repo_id: int, limit: int = 5):
    """Repos most similar to this one, by TF-IDF cosine similarity over
    each repo's summary/description/language. Unsupervised — no training
    data required, recomputed fresh from whatever's currently saved."""
    conn = get_connection()
    try:
        rows = [dict(r) for r in conn.execute("SELECT * FROM repositories").fetchall()]
    finally:
        conn.close()
    if not any(r["id"] == repo_id for r in rows):
        raise HTTPException(status_code=404, detail="Repository not found")
    return similarity_model.find_similar(repo_id, rows, top_n=limit)


@app.get("/api/anomalies", response_model=AnomalyReportResponse)
def get_anomaly_report():
    """Flags saved repos whose stats look statistically unusual relative to
    the rest of your saved set, via Isolation Forest. Unsupervised — no
    training data required, but needs a minimum number of saved repos to
    produce meaningful output."""
    conn = get_connection()
    try:
        rows = [dict(r) for r in conn.execute("SELECT * FROM repositories").fetchall()]
    finally:
        conn.close()
    results = anomaly_model.detect_anomalies(rows)
    if results is None:
        return {"available": False, "min_repos_required": anomaly_model.MIN_REPOS_FOR_ANOMALY, "results": []}
    return {"available": True, "min_repos_required": anomaly_model.MIN_REPOS_FOR_ANOMALY, "results": results}


@app.get("/api/ml-status")
def get_ml_status():
    """Which learned (dataset-dependent) models are currently trained and active."""
    return {
        "health_classifier_trained": health_classifier.is_available(),
        "category_classifier_trained": category_classifier.is_available(),
    }
