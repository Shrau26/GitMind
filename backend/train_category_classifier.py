"""Train the README category/tag classifier.

Usage:
    python3 train_category_classifier.py path/to/category_dataset.csv

Expected CSV columns (header row required):
    text, category

Where `text` is README content and/or description (concatenate them
yourself if you have both — one text column keeps this simple), and
`category` is whatever label taxonomy you choose, e.g.:
    web-framework, cli-tool, ml-library, game, mobile-app, documentation,
    data-tool, infrastructure, other

Rule of thumb: aim for a few hundred labeled rows per category. The
recommended way to get a large REAL dataset (~3,000 rows; repos labelled by
their author-assigned GitHub topics, text = description + README) is:

    python3 scripts/collect_github_datasets.py
TF-IDF + logistic regression (used here) is a solid, fast baseline for
small-to-medium text classification datasets — it won't match a large
pretrained language model's accuracy, but it's honest about needing no
internet access and no huge compute budget.

On success, writes models/category_classifier.joblib (a full sklearn
Pipeline: TfidfVectorizer -> LogisticRegression). The backend picks it up
automatically on next restart; no other code changes needed.
"""

import sys
from pathlib import Path

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.metrics import accuracy_score, classification_report
from sklearn.pipeline import Pipeline

REQUIRED_COLUMNS = ["text", "category"]
MODEL_OUT = Path(__file__).resolve().parent / "models" / "category_classifier.joblib"


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    csv_path = Path(sys.argv[1])
    if not csv_path.exists():
        print(f"File not found: {csv_path}")
        sys.exit(1)

    df = pd.read_csv(csv_path).dropna(subset=REQUIRED_COLUMNS)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        print(f"Dataset is missing required columns: {missing}")
        sys.exit(1)

    for label, count in df["category"].value_counts().items():
        if count < 8:
            print(f"Warning: only {count} rows for category '{label}'. "
                  f"Predictions for this class will likely be unreliable.")

    X = df["text"].astype(str).values
    y = df["category"].values

    class_counts = df["category"].value_counts()
    can_stratify = len(class_counts) > 1 and class_counts.min() >= 2
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42,
        stratify=y if can_stratify else None,
    )

    def make_pipeline():
        return Pipeline([
            ("tfidf", TfidfVectorizer(stop_words="english", max_features=30000,
                                      ngram_range=(1, 2), sublinear_tf=True, min_df=2)),
            ("clf", LogisticRegression(max_iter=2000, C=8.0, class_weight="balanced")),
        ])

    pipeline = make_pipeline()
    pipeline.fit(X_train, y_train)

    print(f"\nDataset: {len(df)} rows ({len(X_train)} train / {len(X_test)} held-out)")
    print("\n--- Held-out evaluation ---")
    y_pred = pipeline.predict(X_test)
    print(classification_report(y_test, y_pred))
    print(f"Held-out accuracy: {accuracy_score(y_test, y_pred):.3f}")

    if can_stratify and class_counts.min() >= 5:
        cv = cross_val_score(make_pipeline(), X, y, cv=5)
        print(f"5-fold cross-validated accuracy: {cv.mean():.3f} (+/- {cv.std():.3f})")

    # Refit on ALL rows for the shipped model.
    pipeline = make_pipeline()
    pipeline.fit(X, y)

    MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, MODEL_OUT)
    print(f"Saved model to {MODEL_OUT}")


if __name__ == "__main__":
    main()
