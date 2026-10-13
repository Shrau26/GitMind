"""Summarizes GitHub Actions workflow-run data into a CI/CD health snapshot.

Fed by github_client.fetch_workflow_runs(), which hits
GET /repos/{owner}/{repo}/actions/runs. That endpoint returns 200 with an
empty list for a repo with no workflows at all — it does not 404 — so an
empty list here means "no CI/CD configured", not an error. See
summarize_ci() below: has_workflows is explicitly False rather than the
caller having to guess from an empty list.
"""

from typing import List, Optional

# Only these two conclusions count as a real pass/fail outcome. "cancelled",
# "skipped", "neutral", "stale", and "action_required" aren't a verdict on
# code health, so they're excluded from the success/failure ratio rather
# than silently counted as failures.
_SUCCESS_CONCLUSIONS = {"success"}
_FAILURE_CONCLUSIONS = {"failure", "timed_out"}


def summarize_ci(workflow_runs: List[dict]) -> dict:
    """workflow_runs: most-recent-first list of {name, status, conclusion,
    created_at, html_url}, as returned by fetch_workflow_runs().

    Returns a dict always shaped the same way, so the frontend/health engine
    never has to special-case "no data" vs. "no workflows" vs. "all green".
    """
    if not workflow_runs:
        return {
            "has_workflows": False,
            "latest_status": None,
            "latest_run_url": None,
            "success_count": 0,
            "failure_count": 0,
            "other_count": 0,
            "failed_workflows": [],
            "last_success_at": None,
            "last_failure_at": None,
            "ci_score": None,
            "sample_size": 0,
        }

    latest = workflow_runs[0]
    latest_status = latest.get("conclusion") or latest.get("status")

    success_count = 0
    failure_count = 0
    other_count = 0
    failed_names = set()
    last_success_at: Optional[str] = None
    last_failure_at: Optional[str] = None

    # workflow_runs is assumed newest-first (GitHub's default order), so the
    # first success/failure encountered while iterating is the most recent.
    for run in workflow_runs:
        conclusion = run.get("conclusion")
        if conclusion in _SUCCESS_CONCLUSIONS:
            success_count += 1
            if last_success_at is None:
                last_success_at = run.get("created_at")
        elif conclusion in _FAILURE_CONCLUSIONS:
            failure_count += 1
            failed_names.add(run.get("name") or "unnamed workflow")
            if last_failure_at is None:
                last_failure_at = run.get("created_at")
        else:
            other_count += 1

    decided = success_count + failure_count
    ci_score = round(100 * success_count / decided, 1) if decided > 0 else None

    return {
        "has_workflows": True,
        "latest_status": latest_status,
        "latest_run_url": latest.get("html_url"),
        "success_count": success_count,
        "failure_count": failure_count,
        "other_count": other_count,
        "failed_workflows": sorted(failed_names),
        "last_success_at": last_success_at,
        "last_failure_at": last_failure_at,
        "ci_score": ci_score,
        "sample_size": len(workflow_runs),
    }
