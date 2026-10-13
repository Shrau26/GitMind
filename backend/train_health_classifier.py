"""Train the learned health-score classifier.

Usage:
    python3 train_health_classifier.py path/to/health_dataset.csv

Expected CSV columns (header row required):
    stars, forks, open_issues, days_since_last_commit, stale_pr_count,
    open_pr_count, label

Where `label` is one of: healthy, fair, at_risk, critical
(same buckets the rule-based heuristic in health.py uses, so the UI badge
colors line up regardless of which scoring path produced the prediction).

Rule of thumb: aim for at least a few hundred labeled rows per class. The
recommended way to get a large REAL dataset (~3,000 rows sampled from live
GitHub repos) is:

    python3 scripts/collect_github_datasets.py

On success, writes models/health_classifier.joblib. The backend picks it up
automatically on next restart; no other code changes needed.
"""

import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.metrics import accuracy_score, classification_report

REQUIRED_COLUMNS = [
    "stars", "forks", "open_issues", "days_since_last_commit",
    "stale_pr_count", "open_pr_count", "label",
]
VALID_LABELS = {"healthy", "fair", "at_risk", "critical"}

MODEL_OUT = Path(__file__).resolve().parent / "models" / "health_classifier.joblib"


def build_features(df: pd.DataFrame) -> np.ndarray:
    issue_ratio = np.where(df["stars"] > 0, df["open_issues"] / df["stars"], df["open_issues"])
    return np.column_stack([
        df["stars"].astype(float),
        df["forks"].astype(float),
        df["open_issues"].astype(float),
        issue_ratio.astype(float),
        df["days_since_last_commit"].astype(float),
        df["stale_pr_count"].astype(float),
        df["open_pr_count"].astype(float),
    ])


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    csv_path = Path(sys.argv[1])
    if not csv_path.exists():
        print(f"File not found: {csv_path}")
        sys.exit(1)

    df = pd.read_csv(csv_path)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        print(f"Dataset is missing required columns: {missing}")
        print(f"Required columns: {REQUIRED_COLUMNS}")
        sys.exit(1)

    bad_labels = set(df["label"].unique()) - VALID_LABELS
    if bad_labels:
        print(f"Found labels outside the expected set {VALID_LABELS}: {bad_labels}")
        sys.exit(1)

    for label, count in df["label"].value_counts().items():
        if count < 10:
            print(f"Warning: only {count} rows for label '{label}'. "
                  f"Predictions for this class will likely be unreliable.")

    X = build_features(df)
    y = df["label"].values

    class_counts = df["label"].value_counts()
    can_stratify = len(class_counts) > 1 and class_counts.min() >= 2
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y if can_stratify else None
    )

    model = RandomForestClassifier(
        n_estimators=300, max_depth=14, min_samples_leaf=2,
        random_state=42, class_weight="balanced", n_jobs=-1,
    )
    model.fit(X_train, y_train)

    print(f"\nDataset: {len(df)} rows ({len(X_train)} train / {len(X_test)} held-out)")
    print("\n--- Held-out evaluation ---")
    y_pred = model.predict(X_test)
    print(classification_report(y_test, y_pred))
    print(f"Held-out accuracy: {accuracy_score(y_test, y_pred):.3f}")

    if can_stratify and class_counts.min() >= 5:
        cv = cross_val_score(
            RandomForestClassifier(n_estimators=150, max_depth=14, min_samples_leaf=2,
                                   random_state=42, class_weight="balanced", n_jobs=-1),
            X, y, cv=5,
        )
        print(f"5-fold cross-validated accuracy: {cv.mean():.3f} (+/- {cv.std():.3f})")

    # Refit on ALL rows for the shipped model — the evaluation above already
    # told us how well this recipe generalises.
    model.fit(X, y)

    MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_OUT)
    print(f"Saved model to {MODEL_OUT}")


if __name__ == "__main__":
    main()
