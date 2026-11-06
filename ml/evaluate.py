"""Check the full Urgency Prediction Engine (rules + model) on hand-written
requests that are NOT part of the training generator.

    python -m ml.evaluate
"""

from ml.predictor import predict_urgency
from ml.validation_examples import EXAMPLES


def evaluate(verbose: bool = False) -> float:
    correct = 0
    for category, title, description, expected in EXAMPLES:
        result = predict_urgency(category, title, description)
        ok = result["label"] == expected
        correct += ok
        if verbose:
            mark = "OK " if ok else "MISS"
            print(f"{mark} expected={expected:8} got={result['label']:8} "
                  f"({result['confidence']:.2f}, {result['source']}) | {description}")
    accuracy = correct / len(EXAMPLES)
    if verbose:
        print(f"\nManual validation accuracy: {correct}/{len(EXAMPLES)} = {accuracy:.0%}")
    return accuracy


if __name__ == "__main__":
    evaluate(verbose=True)
