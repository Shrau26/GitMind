"""Summarizes branch data into total/active/stale counts and flags branches
with long-dead activity.

Fed by a list of {name, last_commit_at} — from github_client's per-branch
commit lookups."""

from datetime import datetime, timezone
from typing import List, Optional

STALE_BRANCH_DAYS = 90     # no commits in this long = stale
HIGH_STALE_COUNT = 3
HIGH_STALE_RATIO = 0.5


def _days_since(iso_date: Optional[str]) -> Optional[float]:
    if not iso_date:
        return None
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400


def summarize_branches(
    default_branch: Optional[str],
    branch_activity: List[dict],
    total_branch_count: Optional[int] = None,
) -> dict:
    """branch_activity: [{name, last_commit_at}, ...] — last_commit_at may
    be None for a branch whose activity couldn't be looked up.
    total_branch_count: exact total if known; falls back to the sample size
    (labeled as such) when not."""

    active = []
    stale = []
    unknown = 0

    for b in branch_activity:
        days = _days_since(b.get("last_commit_at"))
        if days is None:
            unknown += 1
            continue
        entry = {"name": b.get("name"), "last_commit_at": b.get("last_commit_at"), "days_since": round(days)}
        if days >= STALE_BRANCH_DAYS:
            stale.append(entry)
        else:
            active.append(entry)

    stale.sort(key=lambda b: b["days_since"], reverse=True)

    sample_size = len(branch_activity)
    stale_ratio = (len(stale) / sample_size) if sample_size > 0 else 0
    high_stale = len(stale) >= HIGH_STALE_COUNT or stale_ratio >= HIGH_STALE_RATIO

    return {
        "available": True,
        "default_branch": default_branch,
        "total_branches": total_branch_count if total_branch_count is not None else sample_size,
        "total_is_exact": total_branch_count is not None,
        "active_branches": len(active),
        "stale_branches": len(stale),
        "unknown_activity": unknown,
        "sample_size": sample_size,
        "stale_branch_list": stale[:10],
        "high_stale_warning": high_stale,
        "warning_message": (
            "Some branches have had no activity for a long time." if high_stale else None
        ),
    }
