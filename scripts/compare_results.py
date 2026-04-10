from pathlib import Path
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]
BASELINE_FILE = ROOT / "experiments" / "baseline.yaml"
CURRENT_FILE = ROOT / "experiments" / "current.yaml"
OUTPUT_FILE = ROOT / "experiments" / "comparison.yaml"
THRESHOLD = 0.05
BASELINE_TAG = "baseline-v1"


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}, got {type(data).__name__}")
    return data


def save_yaml(path: Path, payload: dict) -> None:
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False)


def load_baseline_from_git_tag() -> tuple[dict, str]:
    tag_check = subprocess.run(
        ["git", "tag", "--list", BASELINE_TAG],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if tag_check.returncode == 0 and tag_check.stdout.strip() == BASELINE_TAG:
        show = subprocess.run(
            ["git", "show", f"{BASELINE_TAG}:experiments/baseline.yaml"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if show.returncode == 0:
            try:
                data = yaml.safe_load(show.stdout)
            except yaml.YAMLError:
                print(f"[WARNING] Failed to parse baseline from {BASELINE_TAG}; falling back to workspace baseline")
                data = None
            if isinstance(data, dict):
                return data, f"git-tag:{BASELINE_TAG}"

    return load_yaml(BASELINE_FILE), "workspace-file"


def enforce_metadata(manifest: dict, name: str) -> None:
    dataset_hash = manifest.get("dataset", {}).get("hash")
    seed = manifest.get("hyperparameters", {}).get("seed")
    if not dataset_hash:
        print(f"[WARNING] Missing dataset.hash in {name} - skipping strict validation")
        return
    if seed is None:
        raise ValueError(f"Policy violation in {name}: missing hyperparameters.seed")


def main() -> None:
    baseline, baseline_source = load_baseline_from_git_tag()
    current = load_yaml(CURRENT_FILE)

    enforce_metadata(baseline, "baseline")
    enforce_metadata(current, "current")

    baseline_acc = float(baseline.get("results", {}).get("accuracy", 0.0))
    current_acc = float(current.get("results", {}).get("accuracy", 0.0))
    baseline_loss = float(baseline.get("results", {}).get("loss", 0.0))
    current_loss = float(current.get("results", {}).get("loss", 0.0))

    accuracy_diff = abs(baseline_acc - current_acc)
    loss_diff = abs(baseline_loss - current_loss)
    divergence = accuracy_diff > THRESHOLD

    result = {
        "baseline_experiment": baseline.get("experiment_id"),
        "current_experiment": current.get("experiment_id"),
        "baseline_source": baseline_source,
        "baseline_tag": BASELINE_TAG,
        "threshold": THRESHOLD,
        "accuracy_diff": round(accuracy_diff, 4),
        "loss_diff": round(loss_diff, 4),
        "divergence": bool(divergence),
    }

    save_yaml(OUTPUT_FILE, result)

    print(f"divergence={str(divergence).lower()}")
    print(
        f"accuracy_diff={result['accuracy_diff']} threshold={THRESHOLD} "
        f"loss_diff={result['loss_diff']}"
    )


if __name__ == "__main__":
    main()
