"""Learned health-score classifier.

Optional — this module is inert until you train a model with
`train_health_classifier.py` (see README for the dataset format). Until
then, `predict()` returns None everywhere it's called and the app falls
back entirely to the rule-based heuristic in `health.py`. Once
`models/health_classifier.joblib` exists, predictions activate
automatically on the next backend restart — no code changes needed.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

import joblib
import numpy as np

MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "health_classifier.joblib"

_model = None
_model_loaded_attempted = False


def _load_model():
    global _model, _model_loaded_attempted
    if _model_loaded_attempted:
        return _model
    _model_loaded_attempted = True
    if MODEL_PATH.exists():
        try:
            _model = joblib.load(MODEL_PATH)
        except Exception:
            _model = None
    return _model


def is_available() -> bool:
    return _load_model() is not None


def _days_since(iso_date: Optional[str]) -> float:
    if not iso_date:
        return 9999.0
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
    except ValueError:
        return 9999.0
    return float((datetime.now(timezone.utc) - dt).days)


def _features(
    stars: int, open_issues: int, forks: int, last_commit_at: Optional[str],
    stale_pr_count: int, open_pr_count: int,
) -> np.ndarray:
    issue_ratio = open_issues / stars if stars > 0 else float(open_issues)
    return np.array([[
        float(stars),
        float(forks),
        float(open_issues),
        float(issue_ratio),
        _days_since(last_commit_at),
        float(stale_pr_count),
        float(open_pr_count),
    ]])


def predict(
    stars: int, open_issues: int, forks: int, last_commit_at: Optional[str],
    stale_pr_count: int, open_pr_count: int,
) -> Optional[Tuple[str, float]]:
    """Return (predicted_label, confidence) or None if no model is trained yet."""
    model = _load_model()
    if model is None:
        return None
    X = _features(stars, open_issues, forks, last_commit_at, stale_pr_count, open_pr_count)
    label = model.predict(X)[0]
    try:
        proba = model.predict_proba(X)[0]
        confidence = float(max(proba))
    except AttributeError:
        confidence = 1.0
    return str(label), round(confidence, 4)
