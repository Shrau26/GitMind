"""Similar-repo recommendations.

Unsupervised — no labeled dataset required. Fits a TF-IDF vectorizer over
each repo's text (summary + description + language + topics + a
dependency-ecosystem token), then ranks the rest by cosine similarity to
the repo you asked about. Refit on every call: with the
handful-to-low-hundreds of repos a tool like this realistically holds,
that's a few milliseconds and keeps the model trivially in sync with
new/deleted repos, so there's no stale cache to invalidate.

This keeps the original TF-IDF approach (nothing here replaces it) and adds
two things on top:
  - a richer text corpus: topics and dependency-manifest-derived ecosystem
    tags feed into the same vectorizer, not just summary/description/language
  - a human-readable "why" explanation per match, built from real shared
    attributes (topics, language, ecosystem) rather than the opaque
    cosine-similarity number alone. When no structured attribute is shared,
    this says so plainly ("similar description wording") instead of
    inventing a reason.
"""

import json
from typing import List, TypedDict

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class SimilarRepo(TypedDict):
    id: int
    full_name: str
    score: float
    similarity_percentage: float
    reasons: List[str]


# Dependency-manifest filename -> a coarse ecosystem tag. This is the same
# real data dependencies.py already parses (manifest_files_found), just
# turned into a token the TF-IDF vectorizer and the explanation logic can
# both use — not a new data source.
_MANIFEST_ECOSYSTEM = {
    "package.json": "javascript-ecosystem",
    "requirements.txt": "python-ecosystem",
    "pyproject.toml": "python-ecosystem",
    "pom.xml": "java-ecosystem",
}


def _safe_json_list(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
    return []


def _safe_json_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


def _topics(row: dict) -> List[str]:
    return [t for t in _safe_json_list(row.get("topics")) if isinstance(t, str) and t.strip()]


def _ecosystems(row: dict) -> List[str]:
    dependency_report = _safe_json_dict(row.get("dependencies"))
    manifests = dependency_report.get("manifest_files_found") or []
    ecosystems = {_MANIFEST_ECOSYSTEM[m] for m in manifests if m in _MANIFEST_ECOSYSTEM}
    return sorted(ecosystems)


def _repo_text(row: dict) -> str:
    topics = _topics(row)
    ecosystems = _ecosystems(row)
    language = row.get("language") or ""
    parts = [
        row.get("summary") or "",
        row.get("description") or "",
        # Light repetition boosts a field's weight in TF-IDF without
        # needing per-field vectorizers — same technique the original
        # code already used for language, now applied consistently.
        (language + " ") * 2,
        (" ".join(topics) + " ") * 3,  # topics are the strongest category signal
        " ".join(ecosystems),
    ]
    return " ".join(p for p in parts if p).strip()


def _explain_similarity(target: dict, other: dict) -> List[str]:
    """Real, checkable reasons two repos matched — never invented. Falls
    back to a generic text-similarity note only when no structured
    attribute is actually shared."""
    reasons = []

    target_topics = set(_topics(target))
    other_topics = set(_topics(other))
    shared_topics = sorted(target_topics & other_topics)
    if shared_topics:
        shown = ", ".join(shared_topics[:5])
        more = f" (+{len(shared_topics) - 5} more)" if len(shared_topics) > 5 else ""
        reasons.append(f"shared topics: {shown}{more}")

    target_lang = (target.get("language") or "").strip()
    other_lang = (other.get("language") or "").strip()
    if target_lang and target_lang.lower() == other_lang.lower():
        reasons.append(f"same primary language: {target_lang}")

    shared_ecosystems = sorted(set(_ecosystems(target)) & set(_ecosystems(other)))
    if shared_ecosystems:
        reasons.append(f"similar dependency stack ({', '.join(shared_ecosystems)})")

    if not reasons:
        reasons.append("similar wording in README/description — no shared topics, language, or dependency stack detected")

    return reasons


def find_similar(target_id: int, all_rows: List[dict], top_n: int = 5) -> List[SimilarRepo]:
    """Return up to top_n repos most similar to the row matching target_id,
    excluding the repo itself. top_n defaults to 5 per spec."""
    if len(all_rows) < 2:
        return []

    texts = [_repo_text(r) for r in all_rows]
    if not any(texts):
        return []

    try:
        vectorizer = TfidfVectorizer(stop_words="english", min_df=1)
        matrix = vectorizer.fit_transform(texts)
    except ValueError:
        # Happens if every document is empty after stopword removal.
        return []

    target_idx = next((i for i, r in enumerate(all_rows) if r["id"] == target_id), None)
    if target_idx is None:
        return []

    target_row = all_rows[target_idx]
    sims = cosine_similarity(matrix[target_idx], matrix).flatten()

    ranked = sorted(
        (
            (score, row)
            for score, row in zip(sims, all_rows)
            if row["id"] != target_id and score > 0
        ),
        key=lambda x: x[0],
        reverse=True,
    )

    results: List[SimilarRepo] = []
    for score, row in ranked[:top_n]:
        results.append({
            "id": row["id"],
            "full_name": row["full_name"],
            "score": round(float(score), 4),
            "similarity_percentage": round(float(score) * 100, 1),
            "reasons": _explain_similarity(target_row, row),
        })
    return results
