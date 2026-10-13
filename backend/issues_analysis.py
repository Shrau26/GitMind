"""Summarizes GitHub issue data into open/closed/stale counts, the oldest
open issue, and average issue age.

Fed by github_client.fetch_issue_search_counts() (exact open/closed counts,
issues only — excludes PRs) and fetch_open_issues_sample() (the actual
oldest-first sample used for staleness/age, since the Search API gives
totals but not the individual issues)."""

from datetime import datetime, timezone
from typing import List, Optional

STALE_ISSUE_DAYS = 30           # no update in this long = stale
HIGH_STALE_COUNT = 15           # absolute count that alone triggers the warning
HIGH_STALE_RATIO = 0.4          # or 40%+ of the sampled open issues being stale


def _days_since(iso_date: Optional[str]) -> Optional[float]:
    if not iso_date:
        return None
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400


def summarize_issues(count_result: dict, open_issues_sample: List[dict]) -> dict:
    """count_result: output of fetch_issue_search_counts().
    open_issues_sample: output of fetch_open_issues_sample() — oldest-first,
    capped at 100."""

    sample_size = len(open_issues_sample)
    stale_count = 0
    ages = []
    oldest = None

    for issue in open_issues_sample:
        age_days = _days_since(issue.get("created_at"))
        if age_days is not None:
            ages.append(age_days)
        staleness_days = _days_since(issue.get("updated_at"))
        if staleness_days is not None and staleness_days >= STALE_ISSUE_DAYS:
            stale_count += 1

    if open_issues_sample:
        # Sample is sorted oldest-created-first.
        oldest_raw = open_issues_sample[0]
        oldest = {
            "number": oldest_raw.get("number"),
            "title": oldest_raw.get("title"),
            "created_at": oldest_raw.get("created_at"),
            "age_days": round(_days_since(oldest_raw.get("created_at")) or 0),
            "html_url": oldest_raw.get("html_url"),
        }

    average_age_days = round(sum(ages) / len(ages)) if ages else None

    stale_ratio = (stale_count / sample_size) if sample_size > 0 else 0
    high_stale = stale_count >= HIGH_STALE_COUNT or stale_ratio >= HIGH_STALE_RATIO

    return {
        "available": count_result.get("available", False),
        "reason": count_result.get("reason"),
        "open_issues": count_result.get("open"),
        "closed_issues": count_result.get("closed"),
        "stale_issues": stale_count if open_issues_sample else None,
        "sample_size": sample_size,
        "sample_is_capped": sample_size >= 100,
        "oldest_open_issue": oldest,
        "average_issue_age_days": average_age_days,
        "high_stale_warning": high_stale,
        "warning_message": (
            "Many stale issues — consider triaging the backlog." if high_stale else None
        ),
    }
