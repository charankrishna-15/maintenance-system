"""Urgency Prediction Engine.

Hybrid approach:
  1. A safety-rule layer catches life-safety phrases (gas leak, sparks,
     flooding ...) and always returns "Critical".
  2. Otherwise the trained TF-IDF + Logistic Regression model predicts one of
     Low / Medium / High / Critical together with class probabilities.
  3. If the model is not confident (top probability < 0.45) the request
     defaults to Medium and the manager can adjust it.
"""

import re
import threading

import joblib

from ml.train_model import MODEL_PATH, build_text, train_and_save

SAFETY_PATTERN = re.compile(
    r"\b("
    r"gas (leak|leaking|smell)|smells? (of|like) gas|leaking gas|"
    r"carbon monoxide|"
    r"sparks?|sparking|"
    r"smoke (is )?(coming|from|in|filling)|smoking|caught fire|on fire|"
    r"flood(ed|ing)|burst pipe|sewage|"
    r"exposed (live )?wires?|electric(al)? shock|short circuit|"
    r"burning smell|burnt smell|"
    r"ceiling (has )?collapsed"
    r")\b",
    re.IGNORECASE,
)

LOW_CONFIDENCE = 0.45

_model = None
_lock = threading.Lock()


def load_model():
    """Load the saved model, training it first if it does not exist yet."""
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                if not MODEL_PATH.exists():
                    train_and_save()
                _model = joblib.load(MODEL_PATH)
    return _model


def predict_urgency(category: str, title: str, description: str) -> dict:
    """Return {label, confidence, probabilities, source}."""
    model = load_model()
    text = build_text(category, title, description)
    probs = model.predict_proba([text])[0]
    probabilities = {cls: float(p) for cls, p in zip(model.classes_, probs)}
    label = max(probabilities, key=probabilities.get)
    confidence = probabilities[label]
    source = "model"

    if SAFETY_PATTERN.search(f"{title} {description}"):
        label = "Critical"
        confidence = max(probabilities.get("Critical", 0.0), 0.95)
        source = "safety-rule"

    # No strong signal: default to Medium rather than guessing an extreme.
    if source == "model" and confidence < LOW_CONFIDENCE:
        label = "Medium"
        confidence = probabilities.get("Medium", 0.0)
        source = "low-confidence-default"

    return {
        "label": label,
        "confidence": round(confidence, 3),
        "probabilities": {k: round(v, 3) for k, v in probabilities.items()},
        "source": source,
    }
