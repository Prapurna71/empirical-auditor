from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPARISON_FILE = ROOT / "experiments" / "comparison.yaml"
CURRENT_FILE = ROOT / "experiments" / "current.yaml"


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}, got {type(data).__name__}")
    return data


def decide_actions(divergence: bool, accuracy_diff: float, metadata: dict, demo: bool) -> dict:
    seed = metadata.get("seed")
    dataset_hash = metadata.get("dataset_hash")

    actions: list[str] = []
    rationale: list[str] = []

    if not divergence:
        severity = "low"
        rationale.append("No divergence detected; preserving minimal analysis path.")
        actions = ["report"]
    elif accuracy_diff < 0.02:
        severity = "low"
        rationale.append("Minor drift below 0.02; bisect skipped as low-impact variance.")
        actions = ["blame", "report"]
    elif accuracy_diff <= 0.05:
        severity = "medium"
        rationale.append("Moderate drift detected; targeted blame + report are required.")
        actions = ["blame", "report"]
    else:
        severity = "high"
        rationale.append("Divergence exceeds 0.05; full forensic analysis is required.")
        actions = ["bisect", "blame", "report", "pr"]

    if seed is None:
        severity = "high"
        rationale.append("Missing seed indicates non-determinism risk; forcing full analysis.")
        actions = ["bisect", "blame", "report", "pr"]

    if not dataset_hash:
        severity = "high"
        rationale.append("Missing dataset hash indicates lineage risk; forcing full analysis.")
        actions = ["bisect", "blame", "report", "pr"]

    if demo:
        severity = "high"
        rationale.append("Demo mode enabled; forcing visible failure-analysis path.")
        actions = ["bisect", "blame", "report", "pr"]

    decision = {
        "severity": severity,
        "actions": actions,
        "reasoning": " ".join(rationale),
        "metadata": {
            "accuracy_diff": round(float(accuracy_diff), 4),
            "divergence": bool(divergence),
            "seed": seed,
            "dataset_hash_present": bool(dataset_hash),
            "demo": bool(demo),
        },
    }
    return decision


def main() -> None:
    parser = argparse.ArgumentParser(description="Decision engine for adaptive analysis pipeline")
    parser.add_argument("--demo", action="store_true", help="Force full analysis path for demo mode")
    args = parser.parse_args()

    comparison = load_yaml(COMPARISON_FILE)
    current = load_yaml(CURRENT_FILE)

    divergence = bool(comparison.get("divergence", False))
    accuracy_diff = float(comparison.get("accuracy_diff", 0.0))
    metadata = {
        "seed": current.get("hyperparameters", {}).get("seed"),
        "dataset_hash": current.get("dataset", {}).get("hash"),
        "python": current.get("environment", {}).get("python"),
        "experiment_id": current.get("experiment_id"),
    }

    decision = decide_actions(divergence, accuracy_diff, metadata, args.demo)
    print(json.dumps(decision, ensure_ascii=True))


if __name__ == "__main__":
    main()
