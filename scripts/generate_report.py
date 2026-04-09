from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
BASELINE_FILE = ROOT / "experiments" / "baseline.yaml"
CURRENT_FILE = ROOT / "experiments" / "current.yaml"
COMPARISON_FILE = ROOT / "experiments" / "comparison.yaml"
BISECT_FILE = ROOT / "experiments" / "bisect_result.yaml"
BLAME_FILE = ROOT / "experiments" / "blame_result.yaml"
REPORT_FILE = ROOT / "memory" / "report.md"


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}, got {type(data).__name__}")
    return data


def compute_repro_score(accuracy_diff: float, divergence: bool) -> int:
    score = max(0.0, 100.0 - (accuracy_diff * 100.0 * 1.5))
    if divergence:
        score -= 20.0
    return int(max(0.0, min(100.0, round(score))))


def main() -> None:
    baseline = load_yaml(BASELINE_FILE)
    current = load_yaml(CURRENT_FILE)
    comparison = load_yaml(COMPARISON_FILE)
    bisect_result = load_yaml(BISECT_FILE)
    blame_result = load_yaml(BLAME_FILE)

    baseline_acc = float(baseline.get("results", {}).get("accuracy", 0.0))
    current_acc = float(current.get("results", {}).get("accuracy", 0.0))
    baseline_loss = float(baseline.get("results", {}).get("loss", 0.0))
    current_loss = float(current.get("results", {}).get("loss", 0.0))

    accuracy_diff = float(comparison.get("accuracy_diff", 0.0))
    divergence = bool(comparison.get("divergence", False))
    repro_score = compute_repro_score(accuracy_diff, divergence)

    root_cause = blame_result.get("root_cause", {}).get("summary", "Unknown")
    suspected_commit = bisect_result.get("first_bad_commit") or "None"

    report = f"""# Reproducibility Audit Report

## Summary

- Baseline experiment: {baseline.get('experiment_id')}
- Current experiment: {current.get('experiment_id')}
- Divergence detected: {str(divergence).lower()}
- Reproducibility score: {repro_score}/100

## Metrics Comparison

| Metric | Baseline | Current | Absolute Difference |
|---|---:|---:|---:|
| Accuracy | {baseline_acc:.4f} | {current_acc:.4f} | {abs(baseline_acc - current_acc):.4f} |
| Loss | {baseline_loss:.4f} | {current_loss:.4f} | {abs(baseline_loss - current_loss):.4f} |

## Root Cause Analysis

- Root cause: {root_cause}
- Suspected commit: {suspected_commit}

## Decision

{'Reject reproducibility: divergence exceeds threshold.' if divergence else 'Approve reproducibility: metrics remain within threshold.'}
"""

    REPORT_FILE.write_text(report, encoding="utf-8")
    print(f"Report generated at {REPORT_FILE}")


if __name__ == "__main__":
    main()
