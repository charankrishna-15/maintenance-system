"""Train the urgency classifier.

    python -m ml.train_model

Pipeline: TF-IDF (word 1-2 grams) -> Logistic Regression.
The model is evaluated on a stratified 20 % hold-out set, then re-fitted on the
full dataset and saved with joblib. Metrics are written to ml/metrics.json.
"""

import json
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from ml.generate_dataset import DATA_PATH, generate

MODEL_PATH = Path(__file__).with_name("urgency_model.joblib")
METRICS_PATH = Path(__file__).with_name("metrics.json")
LABELS = ["Low", "Medium", "High", "Critical"]


def build_text(category: str, title: str, description: str) -> str:
    return f"{category} {title} {description}".lower()


def build_pipeline() -> Pipeline:
    return Pipeline(
        [
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)),
            ("clf", LogisticRegression(max_iter=2000, C=4.0, class_weight="balanced")),
        ]
    )


def train_and_save(verbose: bool = False) -> dict:
    df = generate()
    df.to_csv(DATA_PATH, index=False)
    texts = [build_text(c, t, d) for c, t, d in zip(df.category, df.title, df.description)]
    y = df["urgency"].tolist()

    x_train, x_test, y_train, y_test = train_test_split(
        texts, y, test_size=0.2, random_state=42, stratify=y
    )
    model = build_pipeline().fit(x_train, y_train)
    pred = model.predict(x_test)

    metrics = {
        "dataset_rows": len(df),
        "train_rows": len(x_train),
        "test_rows": len(x_test),
        "accuracy": round(float(accuracy_score(y_test, pred)), 4),
        "labels": LABELS,
        "confusion_matrix": confusion_matrix(y_test, pred, labels=LABELS).tolist(),
        "report": classification_report(
            y_test, pred, labels=LABELS, output_dict=True, zero_division=0
        ),
    }
    METRICS_PATH.write_text(json.dumps(metrics, indent=2))

    # Final model uses all of the data.
    final_model = build_pipeline().fit(texts, y)
    joblib.dump(final_model, MODEL_PATH)

    if verbose:
        print(f"Hold-out accuracy: {metrics['accuracy']:.3f}")
        print(classification_report(y_test, pred, labels=LABELS, zero_division=0))
        print("Confusion matrix (rows = true, cols = predicted):", LABELS)
        for row in metrics["confusion_matrix"]:
            print(row)
        print(f"Saved model to {MODEL_PATH}")
    return metrics


if __name__ == "__main__":
    train_and_save(verbose=True)
