"""Summarizes release data into latest version, total count, time since
latest, and release frequency.

Fed by github_client.fetch_releases() (a recent sample, richest data) and
fetch_release_total_count() (an exact total via the Link-header trick) for
GitHub repos, in a {tag_name, name, published_at} shape."""

from datetime import datetime, timezone
from typing import List, Optional


def _days_since(iso_date: Optional[str]) -> Optional[float]:
    if not iso_date:
        return None
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400


def summarize_releases(releases_sample: List[dict], total_release_count: Optional[int] = None) -> dict:
    """releases_sample: [{tag_name, name, published_at}, ...], any order.
    total_release_count: exact total if known (e.g. from the Link-header
    trick, or an exact local git-tag count); None if unknown."""

    dated = sorted(
        (r for r in releases_sample if r.get("published_at")),
        key=lambda r: r["published_at"],
        reverse=True,
    )

    if not dated:
        return {
            "available": True,
            "has_releases": False,
            "message": "No releases detected.",
            "latest_release": None,
            "total_releases": total_release_count or 0,
            "total_is_exact": total_release_count is not None,
            "days_since_latest": None,
            "release_frequency_days": None,
            "sample_size": 0,
        }

    latest = dated[0]
    days_since_latest = _days_since(latest["published_at"])

    release_frequency_days = None
    if len(dated) >= 2:
        gaps = []
        for i in range(len(dated) - 1):
            d1 = datetime.fromisoformat(dated[i]["published_at"].replace("Z", "+00:00"))
            d2 = datetime.fromisoformat(dated[i + 1]["published_at"].replace("Z", "+00:00"))
            gaps.append((d1 - d2).total_seconds() / 86400)
        if gaps:
            release_frequency_days = round(sum(gaps) / len(gaps), 1)

    return {
        "available": True,
        "has_releases": True,
        "message": None,
        "latest_release": {
            "tag_name": latest.get("tag_name"),
            "name": latest.get("name") or latest.get("tag_name"),
            "published_at": latest.get("published_at"),
            "days_since": round(days_since_latest) if days_since_latest is not None else None,
        },
        "total_releases": total_release_count if total_release_count is not None else len(dated),
        "total_is_exact": total_release_count is not None,
        "days_since_latest": round(days_since_latest) if days_since_latest is not None else None,
        "release_frequency_days": release_frequency_days,
        "sample_size": len(dated),
    }
