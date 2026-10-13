"""Gemini-powered GitMind AI Advisor.

The advisor never receives the repository wholesale. A small question classifier
selects only the structured evidence relevant to the question, then Gemini
explains deterministic GitMind results. All calculations remain local.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any

import httpx

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
MAX_CONTEXT_CHARS = 12000
MAX_OUTPUT_TOKENS = 260
REQUEST_TIMEOUT_SECONDS = 20
CACHE_TTL_SECONDS = 600
_CACHE_MAX_ITEMS = 128
_CACHE: dict[str, tuple[float, str]] = {}

SYSTEM_PROMPT = """You are GitMind AI Advisor. Answer using only the GitMind evidence supplied in the request. Never invent repository facts. Clearly distinguish verified facts from interpretations and recommendations. If evidence is insufficient, say so explicitly. Be concise and practical; do not repeat large amounts of repository data. Do not fabricate files, vulnerabilities, contributors, commits, metrics, dependencies, or statistics.

Return a clean, concise response using these labeled sections (omit a section only if it genuinely does not apply):
FACT: One or two verified findings from the supplied evidence.
INFERENCE: What those findings may indicate; make clear this is an interpretation.
RECOMMENDATION: One to three prioritized, actionable next steps.
UNKNOWN: Important details the supplied evidence cannot confirm.
CONFIDENCE: High, Medium, or Low, based on evidence quality.

Do not include raw JSON dumps or internal implementation details. Summarize only the most relevant evidence in plain language. If evidence is insufficient, state: Insufficient repository evidence to confirm this. Never present an inference or forecast as a fact."""

class AdvisorError(Exception):
    def __init__(self, message: str, status_code: int = 502, code: str = "advisor_unavailable"):
        self.message = message
        self.status_code = status_code
        self.code = code
        super().__init__(message)


def _dict(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            v = json.loads(value)
            return v if isinstance(v, dict) else {}
        except Exception:
            return {}
    return {}


def _list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            v = json.loads(value)
            return v if isinstance(v, list) else []
        except Exception:
            return []
    return []


def classify_question(question: str) -> str:
    q = question.lower()
    if (
        "why did health improve" in q
        or "health score improved" in q
        or "health score improve" in q
        or any(k in q for k in ("forecast", "future", "predict", "degrad", "paradox", "warning", "risk pathway", "intervention"))
    ):
        return "predictive"
    if any(k in q for k in ("security", "vulnerab", "secret", "exploit", "safe", "cve", "dependabot")):
        return "security"
    if (
        any(k in q for k in ("test", "testing", "coverage", "pipeline", "continuous integration"))
        or " ci " in f" {q} "
    ):
        return "testing"
    if any(k in q for k in ("dependenc", "package", "library", "outdated")):
        return "dependency"
    if any(k in q for k in ("health", "score", "issue", "pr", "pull request", "contributor", "activity", "quality")):
        return "health"
    return "general"


def _common(repo: dict) -> dict:
    return {
        "repository": repo.get("full_name"),
        "health": {
            "score": repo.get("health_score"),
            "status": repo.get("health_status"),
            "risk_flags": _list(repo.get("risk_flags"))[:5],
        },
    }


def build_evidence(repo: dict, question: str, latest_digest: str | None = None, predictive: dict | None = None) -> dict:
    """Return only the structured evidence relevant to the classified question."""
    kind = classify_question(question)
    deps = _dict(repo.get("dependencies"))
    security = _dict(deps.get("security"))
    testing = _dict(repo.get("testing_analysis"))
    ci = _dict(repo.get("ci_cd"))
    contributor = _dict(repo.get("contributor_analysis"))
    pr = _dict(repo.get("pr_analysis"))
    breakdown = _dict(repo.get("health_breakdown"))

    if kind == "security":
        evidence = {
            **_common(repo),
            "security": {
                "security_score": security.get("security_score"),
                "available": security.get("available"),
                "critical": security.get("critical"),
                "high": security.get("high"),
                "medium": security.get("medium"),
                "low": security.get("low"),
                "findings": _list(security.get("alerts"))[:5],
            },
            "dependency_security": {
                "dependency_health_score": deps.get("dependency_health_score"),
                "per_dependency_risk": _list(deps.get("per_dependency_risk", {}).get("dependencies") if isinstance(deps.get("per_dependency_risk"), dict) else [])[:5],
            },
        }
    elif kind == "testing":
        evidence = {
            **_common(repo),
            "testing": {
                "analysis": testing,
                "health_factor": breakdown.get("testing"),
                "ci": {
                    "ci_score": ci.get("ci_score"),
                    "success_count": ci.get("success_count"),
                    "failure_count": ci.get("failure_count"),
                    "sample_size": ci.get("sample_size"),
                },
            },
        }
    elif kind == "dependency":
        evidence = {
            **_common(repo),
            "dependencies": {
                "manifest_files_found": deps.get("manifest_files_found"),
                "total_dependencies": deps.get("total_dependencies"),
                "transitive": deps.get("transitive"),
                "dependency_health_score": deps.get("dependency_health_score"),
                "dependency_health_level": deps.get("dependency_health_level"),
                "security": {
                    "available": security.get("available"),
                    "critical": security.get("critical"),
                    "high": security.get("high"),
                    "medium": security.get("medium"),
                    "low": security.get("low"),
                },
            },
        }
    elif kind == "predictive":
        evidence = {
            **_common(repo),
            "predictive_repository_risk": predictive or {
                "available": False,
                "message": "Forecast requires additional repository history.",
            },
        }
    elif kind == "health":
        evidence = {
            **_common(repo),
            "health_components": {
                k: v for k, v in breakdown.items()
                if isinstance(v, dict) and v.get("available")
            },
            "history_relevant": {
                "open_issues": repo.get("open_issues"),
                "open_pr_count": repo.get("open_pr_count"),
                "stale_pr_count": repo.get("stale_pr_count"),
                "contributor_count": repo.get("contributor_count"),
                "contributor_concentration": contributor.get("top1_percentage"),
                "pr_backlog": pr.get("stale_prs"),
            },
        }
    else:
        evidence = {
            **_common(repo),
            "activity": {
                "last_commit_at": repo.get("last_commit_at"),
                "open_issues": repo.get("open_issues"),
                "open_pr_count": repo.get("open_pr_count"),
                "stale_pr_count": repo.get("stale_pr_count"),
                "contributors": repo.get("contributor_count"),
            },
        }

    if latest_digest and kind in {"security", "health", "general"}:
        evidence["recent_change"] = latest_digest[:500]

    # Compact JSON is easier to bound and avoids accidental raw repository dumps.
    encoded = json.dumps(evidence, separators=(",", ":"), ensure_ascii=False)
    if len(encoded) > MAX_CONTEXT_CHARS:
        # Drop optional noisy fields before truncating; never cut JSON into an
        # invalid object that could confuse the model.
        for key in ("security", "dependencies", "health_components", "history_relevant", "activity"):
            if isinstance(evidence.get(key), dict):
                evidence[key] = {k: v for k, v in evidence[key].items() if k not in {"findings", "per_dependency_risk", "analysis"}}
        encoded = json.dumps(evidence, separators=(",", ":"), ensure_ascii=False)
    if len(encoded) > MAX_CONTEXT_CHARS:
        # Keep the payload valid JSON even for unexpectedly verbose stored
        # analyses; never send a truncated JSON fragment to Gemini.
        evidence = {
            "repository": repo.get("full_name"),
            "health": {
                "score": repo.get("health_score"),
                "status": repo.get("health_status"),
                "risk_flags": _list(repo.get("risk_flags"))[:3],
            },
            "topic": kind,
            "note": "Detailed evidence was omitted because the advisor input limit was reached.",
        }
        encoded = json.dumps(evidence, separators=(",", ":"), ensure_ascii=False)
    return {"topic": kind, "evidence": encoded}


def _cache_get(key: str) -> str | None:
    item = _CACHE.get(key)
    if not item:
        return None
    created, value = item
    if time.time() - created > CACHE_TTL_SECONDS:
        _CACHE.pop(key, None)
        return None
    return value


def _cache_put(key: str, value: str) -> None:
    if len(_CACHE) >= _CACHE_MAX_ITEMS:
        oldest = min(_CACHE.items(), key=lambda item: item[1][0])[0]
        _CACHE.pop(oldest, None)
    _CACHE[key] = (time.time(), value)


async def ask_about_repo(repo: dict, question: str, latest_digest: str = None, predictive: dict = None) -> str:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise AdvisorError("Gemini API key is not configured.", status_code=503, code="missing_api_key")

    question = question.strip()
    if not question:
        raise AdvisorError("Question cannot be empty.", status_code=400, code="invalid_question")

    selected = build_evidence(repo, question, latest_digest, predictive)
    cache_key = hashlib.sha256(
        f"{DEFAULT_MODEL}|{question}|{selected['topic']}|{selected['evidence']}".encode("utf-8")
    ).hexdigest()
    cached = _cache_get(cache_key)
    if cached:
        return cached

    user_content = (
        f"QUESTION:\n{question[:1000]}\n\n"
        f"TOPIC: {selected['topic']}\n"
        f"GITMIND EVIDENCE (only source of repository facts):\n{selected['evidence']}"
    )
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": user_content}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": MAX_OUTPUT_TOKENS,
        },
    }
    url = f"{GEMINI_API_BASE}/{DEFAULT_MODEL}:generateContent"
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(url, headers=headers, json=payload)
    except httpx.TimeoutException as exc:
        raise AdvisorError("Gemini request timed out.", status_code=504, code="timeout") from exc
    except httpx.RequestError as exc:
        raise AdvisorError("Gemini is temporarily unreachable.", status_code=502, code="network") from exc

    if response.status_code in (400, 401, 403):
        raise AdvisorError("Gemini rejected the request or API key. Check GEMINI_API_KEY and Gemini API access.", status_code=502, code="api_key_or_request")
    if response.status_code == 429:
        raise AdvisorError("Gemini free-tier/rate limit reached. Try again later.", status_code=429, code="rate_limit")
    if response.status_code >= 500:
        raise AdvisorError("Gemini is temporarily unavailable.", status_code=502, code="provider")

    try:
        data = response.json()
        text = "\n".join(
            part.get("text", "")
            for candidate in data.get("candidates", [])
            for part in candidate.get("content", {}).get("parts", [])
            if isinstance(part, dict) and part.get("text")
        ).strip()
    except (ValueError, AttributeError, TypeError) as exc:
        raise AdvisorError("Unexpected response from Gemini.", status_code=502, code="bad_response") from exc

    if not text:
        raise AdvisorError("Gemini returned no answer.", status_code=502, code="empty_response")

    # Protect the UI and token budget even if the provider ignores maxOutputTokens.
    text = text[:4000]
    _cache_put(cache_key, text)
    return text
