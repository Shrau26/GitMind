"""Anomaly/outlier detection across your saved repos.

Unsupervised — no labeled dataset required. Trains a fresh Isolation Forest
on every call over the numeric feature vector of every repo currently saved
(stars, forks, open issues, issue ratio, days since last commit, stale PR
count). Isolation Forest is a genuine, if small, trained model: it builds an
ensemble of random partitioning trees and scores each point by how few
splits it takes to isolate it — points that split off quickly (few splits)
are the outliers. Retraining per-request is intentional for the same reason
as similarity.py: the "dataset" here is just whatever you've saved, and it's
small enough that refitting is instant and always current.

Needs at least MIN_REPOS_FOR_ANOMALY saved repos to produce meaningful
results; below that, results are marked as unavailable rather than guessed.
"""

from datetime import datetime, timezone
from typing import List, Optional, TypedDict

import numpy as np
from sklearn.ensemble import IsolationForest

MIN_REPOS_FOR_ANOMALY = 5


class AnomalyResult(TypedDict):
    id: int
    full_name: str
    is_anomaly: bool
    anomaly_score: float


def _days_since(iso_date: Optional[str]) -> float:
    if not iso_date:
        return 9999.0
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
    except ValueError:
        return 9999.0
    return float((datetime.now(timezone.utc) - dt).days)


def _feature_vector(row: dict) -> List[float]:
    stars = row.get("stars", 0) or 0
    issue_ratio = (row.get("open_issues", 0) or 0) / stars if stars > 0 else float(row.get("open_issues", 0) or 0)
    return [
        float(stars),
        float(row.get("forks", 0) or 0),
        float(row.get("open_issues", 0) or 0),
        float(issue_ratio),
        _days_since(row.get("last_commit_at")),
        float(row.get("stale_pr_count", 0) or 0),
    ]


def detect_anomalies(all_rows: List[dict]) -> Optional[List[AnomalyResult]]:
    """Return per-repo anomaly results, or None if there aren't enough repos yet."""
    if len(all_rows) < MIN_REPOS_FOR_ANOMALY:
        return None

    X = np.array([_feature_vector(r) for r in all_rows])

    model = IsolationForest(
        n_estimators=150,
        contamination="auto",
        random_state=42,
    )
    model.fit(X)
    predictions = model.predict(X)          # -1 = anomaly, 1 = normal
    raw_scores = model.decision_function(X)  # higher = more normal

    results: List[AnomalyResult] = []
    for row, pred, score in zip(all_rows, predictions, raw_scores):
        results.append(
            {
                "id": row["id"],
                "full_name": row["full_name"],
                "is_anomaly": bool(pred == -1),
                # Flip sign so higher = more anomalous, which reads more naturally in the UI.
                "anomaly_score": round(float(-score), 4),
            }
        )

    results.sort(key=lambda r: r["anomaly_score"], reverse=True)
    return results
