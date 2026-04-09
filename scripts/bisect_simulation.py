from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_FILE = ROOT / "experiments" / "bisect_result.yaml"
THRESHOLD = 0.05


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}, got {type(data).__name__}")
    return data


def save_yaml(path: Path, payload: dict) -> None:
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False)


def run_git(cwd: Path, args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=check,
    )


def get_original_ref() -> str:
    branch = run_git(ROOT, ["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
    if branch == "HEAD":
        return run_git(ROOT, ["rev-parse", "HEAD"]).stdout.strip()
    return branch


def get_commit_history(repo_dir: Path) -> list[tuple[str, str]]:
    log_output = run_git(repo_dir, ["log", "--oneline"]).stdout.strip().splitlines()
    history: list[tuple[str, str]] = []
    for line in log_output:
        parts = line.split(" ", 1)
        if len(parts) == 2:
            history.append((parts[0], parts[1]))
    history.reverse()
    return history


def run_experiment_at_commit(repo_dir: Path) -> None:
    subprocess.run(
        [sys.executable, str(repo_dir / "scripts" / "run_experiment.py")],
        cwd=repo_dir,
        check=True,
    )


def measure_accuracy_diff(repo_dir: Path) -> float:
    baseline = load_yaml(repo_dir / "experiments" / "baseline.yaml")
    current = load_yaml(repo_dir / "experiments" / "current.yaml")
    baseline_acc = float(baseline.get("results", {}).get("accuracy", 0.0))
    current_acc = float(current.get("results", {}).get("accuracy", 0.0))
    return abs(baseline_acc - current_acc)


def reset_run_artifacts(repo_dir: Path) -> None:
    run_git(repo_dir, ["checkout", "--", "experiments/current.yaml"], check=False)


def main() -> None:
    original_ref = get_original_ref()
    original_head = run_git(ROOT, ["rev-parse", "HEAD"]).stdout.strip()

    with tempfile.TemporaryDirectory(prefix="empirical-auditor-bisect-") as temp_dir:
        worktree_dir = Path(temp_dir)
        run_git(ROOT, ["worktree", "add", "--detach", str(worktree_dir), original_ref])

        try:
            history = get_commit_history(worktree_dir)

            if not history:
                payload = {
                    "divergence": False,
                    "first_bad_commit": None,
                    "message": "No commits found.",
                    "history_size": 0,
                }
                save_yaml(OUTPUT_FILE, payload)
                print("No commits found.")
                return

            first_bad_commit = None
            first_bad_message = None
            inspected: list[dict] = []

            for commit, message in history:
                run_git(worktree_dir, ["checkout", commit])
                run_experiment_at_commit(worktree_dir)
                accuracy_diff = measure_accuracy_diff(worktree_dir)
                is_bad = accuracy_diff > THRESHOLD

                inspected.append(
                    {
                        "commit": commit,
                        "message": message,
                        "accuracy_diff": round(accuracy_diff, 4),
                        "good": not is_bad,
                    }
                )

                print(
                    f"commit={commit} accuracy_diff={round(accuracy_diff, 4)} "
                    f"status={'bad' if is_bad else 'good'}"
                )

                reset_run_artifacts(worktree_dir)

                if is_bad:
                    first_bad_commit = commit
                    first_bad_message = message
                    break

            payload = {
                "divergence": first_bad_commit is not None,
                "first_bad_commit": first_bad_commit,
                "commit_message": first_bad_message,
                "threshold": THRESHOLD,
                "history_size": len(history),
                "inspected": inspected,
            }
            save_yaml(OUTPUT_FILE, payload)

            if first_bad_commit is None:
                print("No bad commit detected.")
            else:
                print(f"first_bad_commit={first_bad_commit}")
                print(f"message={first_bad_message}")
        finally:
            run_git(ROOT, ["worktree", "remove", "--force", str(worktree_dir)], check=False)

    # Ensure the caller repository remains on its original HEAD.
    current_head = run_git(ROOT, ["rev-parse", "HEAD"]).stdout.strip()
    if current_head != original_head:
        run_git(ROOT, ["checkout", original_ref])


if __name__ == "__main__":
    main()
