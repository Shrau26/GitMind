"""Turns two consecutive repo_snapshots rows into a short, human-readable
"what changed" line — e.g. "+120 stars · health 74 -> 81 (+7) · 2 new
contributors". Pure and deterministic: same two snapshots always produce
the same digest, and nothing here talks to the network or the database —
main.py fetches the previous snapshot, calls build_digest(), and stores the
result on the *new* snapshot row via database.record_snapshot().
"""

from typing import Optional


def _signed(n: int) -> str:
    return f"+{n}" if n > 0 else str(n)


def build_digest(previous: Optional[dict], current: dict) -> str:
    """`previous` is the prior repo_snapshots row (or None if this repo has
    never been analyzed before). `current` holds the same fields for the
    snapshot about to be inserted. Returns one short sentence — never more
    than a handful of clauses, so it reads as a headline, not a diff dump."""
    if previous is None:
        return "Initial analysis — baseline recorded."

    clauses = []

    def delta(field, label, unit=""):
        prev_val = previous.get(field)
        cur_val = current.get(field)
        if prev_val is None or cur_val is None:
            return
        change = cur_val - prev_val
        if change == 0:
            return
        clauses.append(f"{_signed(change)} {label}{unit}")

    delta("stars", "stars")
    delta("contributor_count", "contributors")
    delta("open_issues", "open issues")
    delta("open_pr_count", "open PRs")

    prev_health = previous.get("health_score")
    cur_health = current.get("health_score")
    if prev_health is not None and cur_health is not None and prev_health != cur_health:
        clauses.append(f"health {prev_health} \u2192 {cur_health} ({_signed(cur_health - prev_health)})")

    prev_security = previous.get("security_score")
    cur_security = current.get("security_score")
    if prev_security is not None and cur_security is not None and prev_security != cur_security:
        clauses.append(f"security score {prev_security} \u2192 {cur_security} ({_signed(cur_security - prev_security)})")

    if not clauses:
        return "No significant changes since last analysis."

    return " \u00b7 ".join(clauses)
