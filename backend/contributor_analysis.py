"""Summarizes contributor data into totals, top contributors, each one's
share of activity, and a concentration/bus-factor warning.

Fed by github_client.fetch_contributors() + fetch_contributor_total_count()."""

from typing import List, Optional

HIGH_CONCENTRATION_THRESHOLD = 70.0  # top contributor's % of sampled commits


def summarize_contributors(
    contributors_sample: List[dict],
    total_contributor_count: Optional[int],
) -> dict:
    """contributors_sample: [{name, commits}, ...] sorted by commits
    descending (both the GitHub and local fetch paths already return it
    this way). total_contributor_count: the real total if known (exact for
    local repos via git shortlog; from the Link-header trick for GitHub
    repos, which can be None if that lookup failed)."""

    if not contributors_sample:
        return {
            "available": False,
            "total_contributors": total_contributor_count,
            "sampled_contributor_count": 0,
            "top_contributors": [],
            "top1_percentage": None,
            "top3_percentage": None,
            "high_concentration": False,
            "concentration_message": None,
        }

    total_sampled_commits = sum(c.get("commits", 0) for c in contributors_sample)

    top_contributors = []
    for c in contributors_sample[:5]:
        commits = c.get("commits", 0)
        pct = round(100 * commits / total_sampled_commits, 1) if total_sampled_commits > 0 else 0.0
        top_contributors.append({"name": c.get("name"), "commits": commits, "activity_percentage": pct})

    top1_pct = top_contributors[0]["activity_percentage"] if top_contributors else 0.0
    top3_commits = sum(c.get("commits", 0) for c in contributors_sample[:3])
    top3_pct = round(100 * top3_commits / total_sampled_commits, 1) if total_sampled_commits > 0 else 0.0

    high_concentration = len(contributors_sample) > 1 and top1_pct >= HIGH_CONCENTRATION_THRESHOLD
    # A repo that's always had exactly one contributor isn't a "concentration
    # risk" discovery so much as its baseline reality — still worth noting,
    # but with the more specific single-contributor language rather than a
    # generic concentration warning (health.py already flags this too).
    single_contributor = len(contributors_sample) == 1 or (total_contributor_count == 1)

    if single_contributor:
        message = None
    elif high_concentration:
        message = "High contributor concentration — possible maintenance risk."
    else:
        message = None

    return {
        "available": True,
        "total_contributors": total_contributor_count,
        "sampled_contributor_count": len(contributors_sample),
        "top_contributors": top_contributors,
        "top1_percentage": top1_pct,
        "top3_percentage": top3_pct,
        "high_concentration": high_concentration,
        "concentration_message": message,
    }
