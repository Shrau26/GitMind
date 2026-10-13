"""Weighted, multi-factor health score and risk flags for a repository.

No ML model here on purpose: with a modest number of interpretable signals
and no labeled "healthy vs. unhealthy" dataset, a hand-tuned weighted
heuristic is more honest and more debuggable than a model "trained" on
nothing. Every weight and threshold lives at the top of this file so the
score is easy to audit or retune.

Nine factors feed the score: activity, issues, pull requests, contributors,
releases, CI/CD, security, testing, and documentation. Each factor is scored
independently on its own 0-100 scale (see the `_*_subscore` functions
below), then combined as a weighted average. Crucially, a factor whose data
simply isn't available (no CI/CD configured, no GitHub token to read
Dependabot alerts, etc.) is *excluded* from the average rather than either
being penalized as 0 or ignored as free credit — its weight is redistributed
proportionally across whatever factors *are* available, so a repo isn't
punished or unfairly boosted just because one signal couldn't be fetched.

Every individual penalty also scales continuously between a "starts to
matter" threshold and a "maxed out" threshold, instead of jumping in one
fixed step. A hard step function (e.g. "-15 if issue ratio >= 15%, else 0")
means every repo that clears that one threshold lands on the exact same
score — a repo at 16% and one at 39% would be scored identically, which
stops being informative once you've analyzed more than a couple of repos.
"""

from datetime import datetime, timezone
from typing import List, Optional, Tuple

# --- Thresholds --------------------------------------------------------------------------
STALE_PR_DAYS = 30
INACTIVITY_WARN_DAYS = 90
INACTIVITY_SEVERE_DAYS = 365
HIGH_ISSUE_RATIO = 0.15    # open issues per star — subscore starts dropping here
SEVERE_ISSUE_RATIO = 0.40  # open issues per star — subscore bottoms out here
HIGH_STALE_PR_COUNT = 5    # stale PR count — subscore bottoms out here
RELEASE_RECENT_DAYS = 120  # release age — subscore starts dropping here
RELEASE_STALE_DAYS = 450   # release age — subscore bottoms out here

# --- Factor weights (must sum to 100) -----------------------------------------------------
WEIGHTS = {
    "activity": 20,
    "issues": 15,
    "pull_requests": 10,
    "contributors": 10,
    "releases": 8,
    "ci_cd": 15,
    "security": 12,
    "testing": 5,
    "documentation": 5,
}
assert sum(WEIGHTS.values()) == 100


def _days_since(iso_date: Optional[str]) -> Optional[int]:
    if not iso_date:
        return None
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - dt).days


def _scaled_penalty(value: float, low: float, high: float, max_penalty: float) -> float:
    """Linearly scale a penalty from 0 (at `low`) to `max_penalty` (at or
    beyond `high`). Returns 0 below `low`."""
    if value <= low:
        return 0.0
    if value >= high:
        return max_penalty
    return max_penalty * (value - low) / (high - low)


# --- Per-factor subscores ------------------------------------------------------------------
# Each returns (score 0-100 or None if not applicable/unknown, optional risk-flag string).

def _activity_subscore(last_commit_at: Optional[str]) -> Tuple[Optional[float], Optional[str]]:
    days = _days_since(last_commit_at)
    if days is None:
        return None, "commit activity unknown"
    score = 100 - _scaled_penalty(days, INACTIVITY_WARN_DAYS, INACTIVITY_SEVERE_DAYS, 100)
    if days >= INACTIVITY_SEVERE_DAYS:
        return score, "no recent activity"
    if days >= INACTIVITY_WARN_DAYS:
        return score, "slowing activity"
    return score, None


def _issues_subscore(stars: int, open_issues: int) -> Tuple[float, Optional[str]]:
    ratio = open_issues / stars if stars > 0 else (1.0 if open_issues > 0 else 0.0)
    score = 100 - _scaled_penalty(ratio, HIGH_ISSUE_RATIO, SEVERE_ISSUE_RATIO, 100)
    if ratio >= SEVERE_ISSUE_RATIO:
        return score, "high open-issue ratio"
    if ratio >= HIGH_ISSUE_RATIO:
        return score, "elevated open-issue ratio"
    return score, None


def _pr_subscore(stale_pr_count: int, open_pr_count: int) -> Tuple[float, Optional[str]]:
    if stale_pr_count <= 0:
        return 100.0, None
    score = 100 - _scaled_penalty(stale_pr_count, 0, HIGH_STALE_PR_COUNT, 100)
    if stale_pr_count >= HIGH_STALE_PR_COUNT:
        return score, "many stale pull requests"
    return score, "some stale pull requests"


def _contributors_subscore(contributor_count: Optional[int]) -> Tuple[Optional[float], Optional[str]]:
    if contributor_count is None:
        return None, None
    if contributor_count <= 1:
        return 35.0, "single-contributor project (bus factor risk)"
    if contributor_count == 2:
        return 60.0, None
    if contributor_count <= 4:
        return 78.0, None
    if contributor_count <= 9:
        return 90.0, None
    return 100.0, None


def _releases_subscore(
    release_count: Optional[int], last_release_at: Optional[str], stars: int
) -> Tuple[Optional[float], Optional[str]]:
    if release_count is None:
        return None, None
    if release_count == 0:
        # Plenty of healthy projects never use GitHub Releases (rolling-release
        # libraries, tag-only workflows) — only flag it for repos big enough
        # that you'd generally expect them.
        flag = "no GitHub releases published" if stars >= 500 else None
        return 55.0, flag
    days = _days_since(last_release_at)
    if days is None:
        return 65.0, None
    score = max(40.0, 100 - _scaled_penalty(days, RELEASE_RECENT_DAYS, RELEASE_STALE_DAYS, 55))
    flag = "no recent releases" if days >= RELEASE_STALE_DAYS else None
    return score, flag


def _ci_subscore(ci_summary: Optional[dict]) -> Tuple[Optional[float], Optional[str]]:
    if not ci_summary or not ci_summary.get("has_workflows"):
        return None, None
    score = ci_summary.get("ci_score")
    if ci_summary.get("latest_status") in ("failure", "timed_out"):
        return score, "most recent CI/CD run failed"
    if score is not None and score < 70:
        return score, "elevated CI/CD failure rate"
    return score, None


def _security_subscore(security_summary: Optional[dict]) -> Tuple[Optional[float], Optional[str]]:
    if not security_summary or not security_summary.get("available"):
        return None, None
    score = security_summary.get("security_score")
    if security_summary.get("critical", 0) > 0:
        return score, "critical security vulnerabilities detected"
    if security_summary.get("high", 0) > 0:
        return score, "high-severity security vulnerabilities detected"
    if security_summary.get("total", 0) > 0:
        return score, "open security vulnerabilities detected"
    return score, None


def _testing_subscore(has_tests: Optional[bool]) -> Tuple[Optional[float], Optional[str]]:
    if has_tests is None:
        return None, None
    if has_tests:
        return 100.0, None
    return 35.0, "no test suite detected"


def _documentation_subscore(doc_score: Optional[float]) -> Tuple[Optional[float], Optional[str]]:
    if doc_score is None:
        return None, None
    flag = "minimal documentation" if doc_score < 40 else None
    return doc_score, flag


def compute_health(
    stars: int,
    open_issues: int,
    last_commit_at: Optional[str],
    stale_pr_count: int,
    open_pr_count: int,
    contributor_count: Optional[int] = None,
    release_count: Optional[int] = None,
    last_release_at: Optional[str] = None,
    ci_summary: Optional[dict] = None,
    security_summary: Optional[dict] = None,
    has_tests: Optional[bool] = None,
    doc_score: Optional[float] = None,
) -> Tuple[int, List[str], dict]:
    """Return (score 0-100, human-readable risk flags, per-factor breakdown).

    All ci_summary / security_summary / contributor_count / release_count /
    has_tests / doc_score arguments are optional: pass None for whatever
    wasn't fetched (e.g. no CI/CD configured), and that factor is excluded
    from the weighted average rather than penalized.
    """

    subscores = {
        "activity": _activity_subscore(last_commit_at),
        "issues": _issues_subscore(stars, open_issues),
        "pull_requests": _pr_subscore(stale_pr_count, open_pr_count),
        "contributors": _contributors_subscore(contributor_count),
        "releases": _releases_subscore(release_count, last_release_at, stars),
        "ci_cd": _ci_subscore(ci_summary),
        "security": _security_subscore(security_summary),
        "testing": _testing_subscore(has_tests),
        "documentation": _documentation_subscore(doc_score),
    }

    breakdown = {}
    flags: List[str] = []
    weighted_sum = 0.0
    total_weight = 0.0

    for factor, (sub_score, sub_flag) in subscores.items():
        weight = WEIGHTS[factor]
        breakdown[factor] = {
            "score": round(sub_score, 1) if sub_score is not None else None,
            "weight": weight,
            "available": sub_score is not None,
        }
        if sub_flag:
            flags.append(sub_flag)
        if sub_score is not None:
            weighted_sum += sub_score * weight
            total_weight += weight

    composite = (weighted_sum / total_weight) if total_weight > 0 else 50.0

    days_inactive = _days_since(last_commit_at)
    if stars >= 1000 and days_inactive is not None and days_inactive < 30:
        composite += 3

    score = max(0, min(100, round(composite)))

    if not flags:
        flags.append("no risk signals detected")

    return score, flags, breakdown


def health_label(score: int) -> str:
    if score >= 80:
        return "Healthy"
    if score >= 55:
        return "Fair"
    if score >= 30:
        return "At Risk"
    return "Critical"
