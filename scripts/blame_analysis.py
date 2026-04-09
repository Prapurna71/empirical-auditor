from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CURRENT_FILE = ROOT / "experiments" / "current.yaml"
COMPARISON_FILE = ROOT / "experiments" / "comparison.yaml"
BISECT_FILE = ROOT / "experiments" / "bisect_result.yaml"
OUTPUT_FILE = ROOT / "experiments" / "blame_result.yaml"


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}, got {type(data).__name__}")
    return data


def save_yaml(path: Path, payload: dict) -> None:
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False)


def infer_root_cause(current: dict, comparison: dict) -> dict:
    dataset_hash = current.get("dataset", {}).get("hash")
    seed = current.get("hyperparameters", {}).get("seed")
    divergence = bool(comparison.get("divergence", False))

    if seed is None:
        return {
            "cause": "seed_missing",
            "summary": "Experiment manifest removed hyperparameters.seed, violating deterministic policy.",
            "severity": "critical",
            "confidence": 0.99,
        }
    if not dataset_hash:
        return {
            "cause": "dataset_hash_missing",
            "summary": "Experiment manifest removed dataset.hash, breaking dataset traceability.",
            "severity": "critical",
            "confidence": 0.99,
        }
    if divergence:
        return {
            "cause": "seed_drift",
            "summary": "Recorded seed differs from baseline behavior and introduced measurable metric divergence.",
            "severity": "high",
            "confidence": 0.91,
        }
    return {
        "cause": "no_issue_detected",
        "summary": "No reproducibility failure detected in current comparison.",
        "severity": "none",
        "confidence": 0.88,
    }


def main() -> None:
    current = load_yaml(CURRENT_FILE)
    comparison = load_yaml(COMPARISON_FILE)
    bisect_result = load_yaml(BISECT_FILE)

    cause = infer_root_cause(current, comparison)

    payload = {
        "root_cause": cause,
        "suspected_commit": bisect_result.get("first_bad_commit"),
        "supporting_evidence": {
            "accuracy_diff": comparison.get("accuracy_diff"),
            "loss_diff": comparison.get("loss_diff"),
            "divergence": comparison.get("divergence"),
        },
    }

    save_yaml(OUTPUT_FILE, payload)
    print(payload)


if __name__ == "__main__":
    main()
