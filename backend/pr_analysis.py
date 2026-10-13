"""Summarizes GitHub pull-request data into open/merged/stale counts,
PRs awaiting review, and average merge time.

Fed by github_client.fetch_open_prs() (open PRs, with draft/review-request
flags already resolved), fetch_pr_merged_count() (exact merged total via
Search API), and fetch_recent_closed_prs() (a recent sample used for the
merge-time calculation, since Search API gives a total but not timestamps)."""

from datetime import datetime, timezone
from typing import List, Optional

STALE_PR_DAYS = 30       # no update in this long = stale (mirrors health.py's own threshold)
HIGH_STALE_COUNT = 5
HIGH_STALE_RATIO = 0.4


def _days_since(iso_date: Optional[str]) -> Optional[float]:
    if not iso_date:
        return None
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400


def summarize_prs(
    open_prs: List[dict],
    merged_count: Optional[int],
    recent_closed_prs: List[dict],
) -> dict:
    """open_prs: fetch_open_prs() output. merged_count: fetch_pr_merged_count()
    output (None if the search API was unavailable). recent_closed_prs:
    fetch_recent_closed_prs() output, used only for the merge-time sample."""

    stale_count = 0
    awaiting_review_count = 0
    for pr in open_prs:
        staleness_days = _days_since(pr.get("updated_at"))
        if staleness_days is not None and staleness_days >= STALE_PR_DAYS:
            stale_count += 1
        if pr.get("awaiting_review"):
            awaiting_review_count += 1

    merge_durations_hours = []
    for pr in recent_closed_prs:
        merged_at = pr.get("merged_at")
        created_at = pr.get("created_at")
        if not merged_at or not created_at:
            continue
        try:
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            merged = datetime.fromisoformat(merged_at.replace("Z", "+00:00"))
        except ValueError:
            continue
        merge_durations_hours.append((merged - created).total_seconds() / 3600)

    avg_merge_hours = round(sum(merge_durations_hours) / len(merge_durations_hours), 1) if merge_durations_hours else None
    avg_merge_days = round(avg_merge_hours / 24, 1) if avg_merge_hours is not None else None

    sample_size = len(open_prs)
    stale_ratio = (stale_count / sample_size) if sample_size > 0 else 0
    high_stale = stale_count >= HIGH_STALE_COUNT or stale_ratio >= HIGH_STALE_RATIO

    return {
        "open_prs": sample_size,
        "sample_is_capped": sample_size >= 100,
        "merged_prs": merged_count,
        "stale_prs": stale_count,
        "awaiting_review": awaiting_review_count,
        "average_merge_time_hours": avg_merge_hours,
        "average_merge_time_days": avg_merge_days,
        "merge_time_sample_size": len(merge_durations_hours),
        "high_stale_warning": high_stale,
        "warning_message": (
            "Many stale pull requests — consider reviewing or closing the backlog." if high_stale else None
        ),
    }
