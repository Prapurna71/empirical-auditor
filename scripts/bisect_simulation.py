from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPARISON_FILE = ROOT / "experiments" / "comparison.yaml"
OUTPUT_FILE = ROOT / "experiments" / "bisect_result.yaml"


SIMULATED_HISTORY = [
    {
        "commit": "a1b2c3d",
        "message": "baseline: stable experiment template",
        "good": True,
    },
    {
        "commit": "b2c3d4e",
        "message": "refactor: manifest layout cleanup",
        "good": True,
    },
    {
        "commit": "c3d4e5f",
        "message": "training: removed explicit stratification",
        "good": True,
    },
    {
        "commit": "d4e5f6g",
        "message": "config: altered random seed policy",
        "good": False,
    },
    {
        "commit": "e5f6g7h",
        "message": "cleanup: accepted drifted metrics",
        "good": False,
    },
]


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}, got {type(data).__name__}")
    return data


def save_yaml(path: Path, payload: dict) -> None:
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False)


def find_first_bad_commit(history: list[dict]) -> dict:
    left = 0
    right = len(history) - 1
    first_bad = None

    while left <= right:
        mid = (left + right) // 2
        if history[mid]["good"]:
            left = mid + 1
        else:
            first_bad = history[mid]
            right = mid - 1

    if first_bad is None:
        return {
            "commit": None,
            "message": "No bad commit detected",
        }
    return first_bad


def main() -> None:
    comparison = load_yaml(COMPARISON_FILE)
    divergence = bool(comparison.get("divergence", False))

    if not divergence:
        payload = {
            "divergence": False,
            "first_bad_commit": None,
            "message": "No divergence. Bisect not required.",
        }
        save_yaml(OUTPUT_FILE, payload)
        print("No divergence. Bisect skipped.")
        return

    first_bad = find_first_bad_commit(SIMULATED_HISTORY)
    payload = {
        "divergence": True,
        "first_bad_commit": first_bad["commit"],
        "commit_message": first_bad["message"],
        "history_size": len(SIMULATED_HISTORY),
    }
    save_yaml(OUTPUT_FILE, payload)

    print(f"first_bad_commit={first_bad['commit']}")
    print(f"message={first_bad['message']}")


if __name__ == "__main__":
    main()
