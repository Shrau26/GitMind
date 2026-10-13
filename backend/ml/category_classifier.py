"""Learned repo category/tag classifier.

Optional — inert until you train a model with `train_category_classifier.py`
(see README for the dataset format). Until then, `predict()` returns None
everywhere it's called. Once `models/category_classifier.joblib` exists,
predictions activate automatically on the next backend restart.

The saved model is a full scikit-learn Pipeline (TfidfVectorizer ->
classifier), so this module doesn't need to know which classifier you chose
when training — it just calls .predict() / .predict_proba() on the pipeline.
"""

from pathlib import Path
from typing import Optional, Tuple

import joblib

MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "category_classifier.joblib"

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


def predict(text: str) -> Optional[Tuple[str, float]]:
    """Return (predicted_category, confidence) or None if no model is trained yet."""
    model = _load_model()
    if model is None or not text or not text.strip():
        return None
    label = model.predict([text])[0]
    try:
        proba = model.predict_proba([text])[0]
        confidence = float(max(proba))
    except AttributeError:
        confidence = 1.0
    return str(label), round(confidence, 4)
