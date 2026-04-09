from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from groq import Groq
import yaml

ROOT = Path(__file__).resolve().parents[1]
CURRENT_FILE = ROOT / "experiments" / "current.yaml"
COMPARISON_FILE = ROOT / "experiments" / "comparison.yaml"
BISECT_FILE = ROOT / "experiments" / "bisect_result.yaml"
OUTPUT_FILE = ROOT / "experiments" / "blame_result.yaml"
ENV_FILE = ROOT / ".env"


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}, got {type(data).__name__}")
    return data


def save_yaml(path: Path, payload: dict) -> None:
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False)


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        raw_line = raw_line.lstrip("\ufeff")
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().lstrip("\ufeff")
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ[key] = value


def run_git(args: list[str], check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=check,
    )


def get_simulated_changes(suspected_commit: str | None) -> dict:
    if not suspected_commit:
        return {
            "summary": "No suspected commit available from bisect.",
            "changed_files": [],
        }

    show = run_git(["show", "--name-only", "--oneline", "--pretty=medium", suspected_commit])
    if show.returncode != 0:
        return {
            "summary": f"Unable to read commit details for {suspected_commit}.",
            "changed_files": [],
        }

    lines = [line.strip() for line in show.stdout.splitlines() if line.strip()]
    changed_files: list[str] = []
    for line in lines:
        if line.endswith(".py") or line.endswith(".yaml") or line.endswith(".md"):
            changed_files.append(line)

    summary = lines[0] if lines else f"Commit {suspected_commit}"
    return {
        "summary": summary,
        "changed_files": changed_files,
    }


def classify_failure(current: dict, comparison: dict) -> str:
    dataset_hash = current.get("dataset", {}).get("hash")
    seed = current.get("hyperparameters", {}).get("seed")
    accuracy_diff = float(comparison.get("accuracy_diff", 0.0))

    if seed is None:
        return "Non-determinism introduced"
    if not dataset_hash:
        return "Data inconsistency"
    if accuracy_diff > 0.1:
        return "Model instability"
    if accuracy_diff > 0.05:
        return "Reproducibility drift"
    return "No critical failure"


def build_attribution(changes: dict, failure_type: str) -> dict:
    changed_files = changes.get("changed_files", [])
    file_name = "experiments/current.yaml"
    if changed_files:
        preferred = [f for f in changed_files if f.startswith("experiments/")]
        file_name = preferred[0] if preferred else changed_files[0]

    line_number = 8 if "current.yaml" in file_name else 1
    change = (
        f"Detected {failure_type.lower()} linked to configuration updates in this file. "
        "Seed/metric related values likely changed relative to baseline expectations."
    )
    return {
        "file": file_name,
        "line": line_number,
        "change": change,
    }


def rule_based_reasoning(current: dict, comparison: dict, changes: dict) -> dict:
    dataset_hash = current.get("dataset", {}).get("hash")
    seed = current.get("hyperparameters", {}).get("seed")
    divergence = bool(comparison.get("divergence", False))
    accuracy_diff = float(comparison.get("accuracy_diff", 0.0))
    loss_diff = float(comparison.get("loss_diff", 0.0))

    if seed is None:
        return {
            "root_cause": (
                "The training seed is missing, so each run can sample different data splits and "
                "model trajectories, making reproducibility unverifiable."
            ),
            "category": "configuration-regression",
            "fix": "Restore hyperparameters.seed in experiment manifests and enforce schema checks in CI.",
        }
    if not dataset_hash:
        return {
            "root_cause": (
                "The dataset fingerprint is missing, so there is no proof that baseline and current "
                "runs use identical source data."
            ),
            "category": "data-lineage-gap",
            "fix": "Restore dataset.hash and block runs when dataset integrity metadata is absent.",
        }
    if divergence:
        changed_files = changes.get("changed_files", [])
        files_text = ", ".join(changed_files) if changed_files else "unknown files"
        return {
            "root_cause": (
                f"Metric drift is significant (accuracy delta {accuracy_diff:.4f}, loss delta {loss_diff:.4f}) and "
                f"aligns with likely configuration changes in {files_text}. The failure pattern matches seed-driven "
                "non-determinism rather than random noise."
            ),
            "category": "reproducibility-drift",
            "fix": (
                "Revert to the last good seed/config commit, pin deterministic split parameters, and add a CI guard "
                "that fails when accuracy drift exceeds 0.05."
            ),
        }
    return {
        "root_cause": "No reproducibility defect detected; observed metrics stay within accepted threshold.",
        "category": "no-issue",
        "fix": "No code change required. Keep monitoring drift and retain deterministic metadata checks.",
    }


def parse_json_object(text: str) -> dict | None:
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    required = {"root_cause", "category", "fix"}
    if not required.issubset(payload.keys()):
        return None
    return {
        "root_cause": str(payload["root_cause"]),
        "category": str(payload["category"]),
        "fix": str(payload["fix"]),
    }


def groq_reasoning(comparison: dict, changes: dict) -> dict | None:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None

    client = Groq(api_key=api_key)
    preferred_model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    candidate_models = [
        preferred_model,
        "llama-3.3-70b-versatile",
        "llama-3.1-70b-versatile",
        "llama-3.1-8b-instant",
    ]
    seen_models: set[str] = set()
    user_prompt = (
        "You are an AI reproducibility engineer. Analyze experiment failure context and return only valid JSON "
        "with keys root_cause, category, fix.\\n\\n"
        f"metric_difference: accuracy_diff={comparison.get('accuracy_diff')}, "
        f"loss_diff={comparison.get('loss_diff')}, divergence={comparison.get('divergence')}\\n"
        f"simulated_diff: {json.dumps(changes)}"
    )

    for model in candidate_models:
        if model in seen_models:
            continue
        seen_models.add(model)

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": user_prompt}],
                temperature=0,
                max_tokens=300,
            )
        except Exception as error:
            print(f"[GROQ_ERROR] {model} {type(error).__name__}: {error}")
            continue

        content = response.choices[0].message.content if response.choices else ""
        if isinstance(content, list):
            content = "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
        if not isinstance(content, str) or not content.strip():
            print(f"[GROQ_ERROR] {model} empty content in response")
            continue

        parsed = parse_json_object(content)
        if parsed is None:
            print(f"[GROQ_ERROR] {model} could not parse JSON text: {content[:500]}")
            continue

        return parsed

    return None


def main() -> None:
    load_env_file(ENV_FILE)

    current = load_yaml(CURRENT_FILE)
    comparison = load_yaml(COMPARISON_FILE)
    bisect_result = load_yaml(BISECT_FILE)

    suspected_commit = bisect_result.get("first_bad_commit")
    changes = get_simulated_changes(suspected_commit)
    failure_type = classify_failure(current, comparison)
    attribution = build_attribution(changes, failure_type)

    explanation = groq_reasoning(comparison, changes)
    reasoning_source = "groq-llm"
    if explanation is None:
        explanation = rule_based_reasoning(current, comparison, changes)
        reasoning_source = "rule-based"

    payload = {
        "root_cause": {
            "summary": explanation["root_cause"],
            "category": explanation["category"],
            "fix": explanation["fix"],
            "source": reasoning_source,
        },
        "llm_explanation": {
            "root_cause": explanation["root_cause"],
            "category": explanation["category"],
            "fix": explanation["fix"],
            "failure_type": failure_type,
        },
        "failure_type": failure_type,
        "attribution": attribution,
        "suspected_commit": suspected_commit,
        "simulated_diff": changes,
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
