"""Deterministic predictive repository risk analysis.

This module deliberately does not call an LLM. It works only with GitMind's
stored repository snapshot history and current deterministic signals.

Forecasts are directional and evidence-based; they do not invent future
metric values or claim causation.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

# Same weights used by health.py / Repository World What-If.
HEALTH_WEIGHTS = {
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

FACTOR_LABELS = {
    "activity": "Activity",
    "issues": "Issues",
    "pull_requests": "Pull requests",
    "contributors": "Contributor concentration",
    "releases": "Releases",
    "ci_cd": "CI/CD",
    "security": "Security",
    "testing": "Testing",
    "documentation": "Documentation",
}

EFFORT = {"Low": 1, "Medium": 2, "High": 3}


def _number(value) -> Optional[float]:
    return float(value) if isinstance(value, (int, float)) and value is not None else None


def _parse_metrics(snapshot: dict) -> dict:
    raw = snapshot.get("metrics_json")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


def _factor_scores(repo: dict) -> dict:
    breakdown = repo.get("health_breakdown") or {}
    if isinstance(breakdown, str):
        try:
            breakdown = json.loads(breakdown)
        except Exception:
            breakdown = {}
    return {
        k: _number(v.get("score"))
        for k, v in breakdown.items()
        if isinstance(v, dict) and v.get("available") and _number(v.get("score")) is not None
    }


def build_current_metrics(repo: dict) -> dict:
    """Build only metrics useful to the predictor from an existing repo row."""
    factors = _factor_scores(repo)
    contrib = repo.get("contributor_analysis") or {}
    pr = repo.get("pr_analysis") or {}
    testing = repo.get("testing_analysis") or {}
    deps = repo.get("dependencies") or {}
    ci = repo.get("ci_cd") or {}
    if isinstance(contrib, str):
        try: contrib = json.loads(contrib)
        except Exception: contrib = {}
    if isinstance(pr, str):
        try: pr = json.loads(pr)
        except Exception: pr = {}
    if isinstance(testing, str):
        try: testing = json.loads(testing)
        except Exception: testing = {}
    if isinstance(deps, str):
        try: deps = json.loads(deps)
        except Exception: deps = {}
    if isinstance(ci, str):
        try: ci = json.loads(ci)
        except Exception: ci = {}

    security = deps.get("security") if isinstance(deps, dict) else {}
    return {
        "health_score": _number(repo.get("health_score")),
        "security_score": (
            _number(security.get("security_score")) if isinstance(security, dict) else None
        ),
        "open_issues": _number(repo.get("open_issues")),
        "open_pr_count": _number(repo.get("open_pr_count")),
        "stale_pr_count": _number(repo.get("stale_pr_count")),
        "contributor_count": _number(repo.get("contributor_count")),
        "contributor_concentration": (
            _number(contrib.get("top1_percentage"))
            if isinstance(contrib, dict) else None
        ),
        "dependency_risk_score": (
            100 - _number(deps.get("dependency_health_score"))
            if isinstance(deps, dict) and _number(deps.get("dependency_health_score")) is not None
            else None
        ),
        "ci_score": _number(ci.get("ci_score")) if isinstance(ci, dict) else None,
        "test_source_ratio": _number(testing.get("test_source_ratio")) if isinstance(testing, dict) else None,
        "factor_scores": factors,
    }


def _series(snapshots: List[dict], metric: str) -> List[Tuple[str, float]]:
    result = []
    for snap in snapshots:
        metrics = _parse_metrics(snap)
        value = metrics.get(metric)
        if value is None and metric in snap:
            value = snap.get(metric)
        value = _number(value)
        if value is not None:
            result.append((snap.get("captured_at") or "", value))
    return result


def _trend(values: List[Tuple[str, float]]) -> Optional[dict]:
    if len(values) < 2:
        return None
    first, last = values[0][1], values[-1][1]
    delta = last - first
    # With only a couple of snapshots, a simple observed delta is more honest
    # than pretending we have a reliable statistical forecast.
    direction = "rising" if delta > 0 else "falling" if delta < 0 else "stable"
    return {"direction": direction, "delta": round(delta, 2), "from": round(first, 2), "to": round(last, 2), "points": len(values)}


def _risk_direction(metric: str, trend: dict) -> Optional[str]:
    if not trend:
        return None
    d = trend["delta"]
    # Higher is riskier for these metrics; lower is riskier for the rest.
    higher_risk = {
        "contributor_concentration", "open_pr_count", "stale_pr_count",
        "open_issues", "dependency_risk_score"
    }
    if metric in higher_risk:
        return "worsening" if d > 0 else "improving" if d < 0 else "stable"
    if metric == "health_score":
        return "improving" if d > 0 else "worsening" if d < 0 else "stable"
    return "improving" if d > 0 else "worsening" if d < 0 else "stable"


def _qualitative_risk(signals: List[dict]) -> str:
    n = len([s for s in signals if s.get("risk_direction") == "worsening"])
    if n >= 4:
        return "HIGH"
    if n >= 2:
        return "MEDIUM"
    return "LOW"


def _confidence(history_points: int, worsening: int, improving: int) -> str:
    if history_points >= 5 and worsening >= 2 and abs(worsening - improving) >= 1:
        return "HIGH"
    if history_points >= 3 or (history_points >= 2 and worsening >= 2):
        return "MEDIUM"
    return "LOW"


def _health_simulation(repo: dict, factor: str, hypothetical: float) -> Optional[int]:
    breakdown = repo.get("health_breakdown") or {}
    if not isinstance(breakdown, dict):
        return None
    weighted_sum = 0.0
    total_weight = 0.0
    for key, weight in HEALTH_WEIGHTS.items():
        info = breakdown.get(key)
        available = isinstance(info, dict) and info.get("available")
        if key == factor:
            score = hypothetical
            available = True
        elif available:
            score = _number(info.get("score"))
        else:
            continue
        if score is None:
            continue
        weighted_sum += score * weight
        total_weight += weight
    if not total_weight:
        return None
    return round(weighted_sum / total_weight)


def _interventions(repo: dict, pathways: List[dict]) -> List[dict]:
    breakdown = repo.get("health_breakdown") or {}
    candidates = []
    problem_factors = set()
    for p in pathways:
        problem_factors.update(p.get("factors", []))

    # Include factors with a currently weak score when they are also part of
    # an observed pathway. No recommendation is produced for unavailable data.
    for factor in problem_factors:
        info = breakdown.get(factor) if isinstance(breakdown, dict) else None
        if not isinstance(info, dict) or not info.get("available"):
            continue
        current = _number(info.get("score"))
        if current is None or current >= 85:
            continue
        target = 90.0 if factor != "security" else 100.0
        simulated = _health_simulation(repo, factor, target)
        baseline = _health_simulation(repo, factor, current)
        if simulated is None or baseline is None:
            continue
        # Use the same weighted-factor baseline as the existing What-If
        # simulator. This avoids confusing the predictor with the small
        # health.py adjustment that can make the displayed current score differ
        # from the raw weighted average.
        impact = simulated - baseline
        effort = {
            "pull_requests": "Low", "contributors": "Low",
            "testing": "Medium", "security": "Medium",
            "ci_cd": "Medium", "documentation": "Low",
            "activity": "High", "issues": "Medium", "releases": "Medium",
        }.get(factor, "Medium")
        if impact <= 0:
            continue
        candidates.append({
            "factor": factor,
            "action": {
                "pull_requests": "Address stale PR backlog",
                "contributors": "Reduce contributor ownership concentration",
                "testing": "Add tests for high-risk modules",
                "security": "Address security findings",
                "ci_cd": "Address recurring CI failures",
                "documentation": "Improve documentation",
                "activity": "Stabilize development activity",
                "issues": "Review the growing issue backlog",
                "releases": "Improve release maintenance",
            }.get(factor, f"Improve {FACTOR_LABELS.get(factor, factor).lower()}"),
            "problem": FACTOR_LABELS.get(factor, factor),
            "simulated_health_impact": int(impact),
            "expected_risk_reduction": "High" if impact >= 6 else "Medium" if impact >= 3 else "Low",
            "estimated_effort": effort,
            "efficiency": round(impact / EFFORT[effort], 2),
            "confidence": "MEDIUM" if len(pathways) >= 1 else "LOW",
            "simulated": True,
        })
    candidates.sort(key=lambda x: x["efficiency"], reverse=True)
    return candidates


def analyze_predictive_risk(repo: dict, snapshots: List[dict]) -> dict:
    """Return a compact deterministic forecast. No future numeric values are fabricated."""
    history = sorted(snapshots or [], key=lambda x: (x.get("captured_at") or "", x.get("id", 0)))
    current_metrics = build_current_metrics(repo)

    # Current snapshot may be absent in older DBs; do not silently backfill it.
    series_metrics = [
        "health_score", "contributor_concentration", "open_pr_count",
        "stale_pr_count", "open_issues", "dependency_risk_score",
    ]
    trends = {}
    signals = []
    for metric in series_metrics:
        values = _series(history, metric)
        tr = _trend(values)
        if tr:
            trends[metric] = tr
            signals.append({
                "metric": metric,
                "risk_direction": _risk_direction(metric, tr),
                "trend": tr,
            })

    # Factor trends are available in new snapshots and are especially useful
    # for testing/CI/security/documentation where raw history was not stored.
    factor_names = list(HEALTH_WEIGHTS)
    factor_trends = {}
    for factor in factor_names:
        values = []
        for snap in history:
            m = _parse_metrics(snap)
            score = (m.get("factor_scores") or {}).get(factor)
            score = _number(score)
            if score is not None:
                values.append((snap.get("captured_at") or "", score))
        tr = _trend(values)
        if tr:
            factor_trends[factor] = tr
            signals.append({
                "metric": factor,
                "risk_direction": "worsening" if tr["delta"] < 0 else "improving" if tr["delta"] > 0 else "stable",
                "trend": tr,
            })

    worsening = [s for s in signals if s["risk_direction"] == "worsening" and s["metric"] != "health_score"]
    improving = [s for s in signals if s["risk_direction"] == "improving" and s["metric"] != "health_score"]

    # Observed pathways only: each pathway requires at least two signals that
    # are present and moving in the compatible risk direction.
    pathways = []
    contrib_worse = _risk_direction("contributor_concentration", trends.get("contributor_concentration") or {}) == "worsening"
    pr_worse = any(
        _risk_direction(m, trends.get(m) or {}) == "worsening"
        for m in ("open_pr_count", "stale_pr_count")
    )
    if contrib_worse and pr_worse:
        pathways.append({
            "name": "Ownership bottleneck → review backlog",
            "factors": ["contributors", "pull_requests"],
            "evidence": [
                "Contributor concentration increased.",
                "Open/stale PR backlog increased.",
            ],
            "relationship": "associated risk pathway observed across repository snapshots; not proof of causation.",
        })

    dep_worse = _risk_direction("dependency_risk_score", trends.get("dependency_risk_score") or {}) == "worsening"
    testing_worse = factor_trends.get("testing", {}).get("delta", 0) < 0
    activity_worse = factor_trends.get("activity", {}).get("delta", 0) < 0
    if dep_worse and testing_worse:
        pathways.append({
            "name": "Dependency risk + weaker testing",
            "factors": ["security", "testing"],
            "evidence": ["Dependency risk increased.", "Testing factor score decreased."],
            "relationship": "associated risk pathway; not proof that one factor caused the other.",
        })
    if activity_worse and testing_worse:
        pathways.append({
            "name": "Lower activity score + weaker testing",
            "factors": ["activity", "testing"],
            "evidence": ["Activity factor score decreased.", "Testing factor score decreased."],
            "relationship": "associated risk pathway; not proof of causation.",
        })

    health_tr = trends.get("health_score")
    direction = "UNKNOWN"
    structural_worsening = len(worsening)
    # A rising composite score does not override a converging structural-risk
    # signal. This is the core "silent degradation" case: health can improve
    # while the underlying repository is moving toward greater risk.
    if structural_worsening >= 2:
        direction = "Deteriorating"
    elif health_tr:
        direction = "Deteriorating" if health_tr["delta"] < 0 else "Improving" if health_tr["delta"] > 0 else "Stable"

    # A forecast needs multiple real snapshots. Two can establish direction,
    # but confidence remains low.
    enough_history = len(history) >= 2 and bool(signals)
    if not enough_history:
        return {
            "available": False,
            "message": "Forecast requires additional repository history.",
            "current_health": current_metrics.get("health_score"),
            "future_direction": "UNKNOWN",
            "risk_level": "UNKNOWN",
            "confidence": "LOW",
            "health_paradox": {"detected": False, "reason": "Insufficient historical structural-risk evidence."},
            "top_risk_pathways": [],
            "recommended_intervention": None,
            "alternative_interventions": [],
            "evidence": [],
        }

    # Health Paradox: health improves while >=2 independent structural-risk
    # indicators worsen in the same observed interval.
    paradox_factors = []
    previous = history[-2] if len(history) >= 2 else None
    latest = history[-1] if history else None
    if previous and latest:
        pm = _parse_metrics(previous)
        lm = _parse_metrics(latest)
        for metric in ("contributor_concentration", "open_pr_count", "stale_pr_count", "open_issues", "dependency_risk_score"):
            a = _number(pm.get(metric)); b = _number(lm.get(metric))
            if a is not None and b is not None and b > a:
                paradox_factors.append(metric)
        for factor in ("testing", "ci_cd", "security"):
            a = _number((pm.get("factor_scores") or {}).get(factor))
            b = _number((lm.get("factor_scores") or {}).get(factor))
            if a is not None and b is not None and b < a:
                paradox_factors.append(factor)
        prev_health = _number(pm.get("health_score"))
        latest_health = _number(lm.get("health_score"))
    else:
        prev_health = latest_health = None

    paradox = bool(prev_health is not None and latest_health is not None and latest_health > prev_health and len(set(paradox_factors)) >= 2)
    paradox_detail = {
        "detected": paradox,
        "reason": (
            "The overall health score improved, but underlying structural-risk indicators deteriorated."
            if paradox else "No health paradox detected in the available adjacent snapshots."
        ),
        "previous_health": prev_health,
        "current_health": latest_health,
        "worsened_factors": sorted(set(paradox_factors)),
    }

    risk_level = _qualitative_risk(worsening)
    conf = _confidence(len(history), len(worsening), len(improving))
    interventions = _interventions(repo, pathways)
    rec = interventions[0] if interventions else None

    evidence = []
    for item in worsening[:5]:
        label = FACTOR_LABELS.get(item["metric"], item["metric"].replace("_", " "))
        evidence.append(f"{label} is {item['trend']['direction']} ({item['trend']['from']} → {item['trend']['to']}).")

    return {
        "available": True,
        "message": None,
        "current_health": current_metrics.get("health_score"),
        "future_direction": direction,
        "risk_level": risk_level,
        "confidence": conf,
        "health_paradox": paradox_detail,
        "top_risk_pathways": pathways[:3],
        "recommended_intervention": rec,
        "alternative_interventions": interventions[1:4],
        "evidence": evidence[:5],
        "history_points": len(history),
        "trends": {**trends, "factor_scores": factor_trends},
    }
