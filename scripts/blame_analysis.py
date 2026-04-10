from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from groq import Groq
import yaml

ROOT = Path(__file__).resolve().parents[1]
BASELINE_FILE = ROOT / "experiments" / "baseline.yaml"
CURRENT_FILE = ROOT / "experiments" / "current.yaml"
COMPARISON_FILE = ROOT / "experiments" / "comparison.yaml"
BISECT_FILE = ROOT / "experiments" / "bisect_result.yaml"
OUTPUT_FILE = ROOT / "experiments" / "blame_result.yaml"
ENV_FILE = ROOT / ".env"
ANALYSIS_TARGET = "scripts/run_experiment.py"


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
        return "Non-determinism"
    if not dataset_hash:
        return "Data drift"
    if accuracy_diff > 0.12:
        return "Hyperparameter instability"
    if accuracy_diff > 0.05:
        return "Code regression"
    return "Code regression"


def parse_diff_signals(diff_text: str) -> dict:
    keywords = ["seed", "shuffle", "random", "batch", "learning_rate"]
    detected_keywords: list[str] = []
    changes: list[dict] = []

    added = 0
    removed = 0
    modified = 0

    for raw_line in diff_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        action = None
        content = line
        if line.startswith("+") and not line.startswith("+++"):
            action = "added"
            added += 1
            content = line[1:].strip()
        elif line.startswith("-") and not line.startswith("---"):
            action = "removed"
            removed += 1
            content = line[1:].strip()
        elif line.startswith("@@"):
            action = "modified"
            modified += 1

        lowered = content.lower()
        for keyword in keywords:
            if keyword in lowered:
                if keyword not in detected_keywords:
                    detected_keywords.append(keyword)
                if action:
                    changes.append({"keyword": keyword, "action": action, "line": content[:160]})

    return {
        "detected_keywords": detected_keywords,
        "changes": changes,
        "change_counts": {
            "added": added,
            "removed": removed,
            "modified": modified,
        },
    }


def build_reasoning_context(diff_signals: dict, metrics: dict) -> dict:
    accuracy_drop = float(metrics.get("accuracy_drop", 0.0))
    if accuracy_drop > 0.1:
        impact_level = "high"
    elif accuracy_drop > 0.05:
        impact_level = "medium"
    else:
        impact_level = "low"

    context = {
        "detected_changes": diff_signals.get("changes", []),
        "metric_shift": {
            "accuracy_drop": accuracy_drop,
            "loss_increase": float(metrics.get("loss_increase", 0.0)),
            "divergence": bool(metrics.get("divergence", False)),
        },
        "impact_level": impact_level,
    }
    return context


def normalize_category(category: str) -> str:
    text = category.lower()
    if "non" in text and "determin" in text:
        return "Non-determinism"
    if "data" in text and ("drift" in text or "inconsisten" in text):
        return "Data drift"
    if "hyper" in text or "learning_rate" in text or "batch" in text:
        return "Hyperparameter instability"
    if "code" in text or "regression" in text:
        return "Code regression"
    return "Code regression"


def enrich_explanation_text(explanation: dict, metrics: dict, current: dict, baseline: dict, diff_text: str) -> dict:
    category = str(explanation.get("category", "Code regression"))
    root_cause = str(explanation.get("root_cause", "")).strip()
    fix = str(explanation.get("fix", "")).strip()

    baseline_acc = float(baseline.get("results", {}).get("accuracy", 0.0))
    current_acc = float(current.get("results", {}).get("accuracy", 0.0))
    accuracy_drop = float(metrics.get("accuracy_drop", 0.0))
    loss_increase = float(metrics.get("loss_increase", 0.0))
    dataset_hash_match = bool(metrics.get("dataset_hash_match", True))

    diff_lower = diff_text.lower()
    seed_related = any(token in diff_lower for token in ["seed", "random_state", "shuffle", "random"])
    history_related = "history_size" in diff_lower
    pipeline_related = any(token in diff_lower for token in ["dataset", "preprocess", "pipeline", "split"])

    if category == "Hyperparameter instability":
        if history_related:
            root_cause = (
                "Change in experiment configuration altered evaluation consistency, leading to unstable accuracy measurements "
                f"(baseline {baseline_acc:.4f} -> current {current_acc:.4f})."
            )
            fix = (
                "Ensure a consistent experiment configuration for metric aggregation, or revert the recent change affecting evaluation; "
                "then rerun baseline and current with identical seed, split, and pipeline settings."
            )
        elif seed_related:
            root_cause = (
                "Hyperparameter changes interacted with seed/randomness controls, producing unstable optimization behavior "
                f"and measurable metric drift (accuracy drop {accuracy_drop:.4f}, loss increase {loss_increase:.4f})."
            )
            fix = (
                "Revert the unstable hyperparameter update, lock seed and random_state values, and validate with repeated runs "
                "under identical train/test split conditions."
            )
        else:
            root_cause = (
                "Recent training-configuration changes likely destabilized evaluation consistency, causing reproducibility drift "
                f"from {baseline_acc:.4f} to {current_acc:.4f} accuracy, especially under repeated runs with the same data path."
            )
            fix = (
                "Restore prior stable hyperparameters and re-run controlled experiments with fixed seed, unchanged data pipeline, "
                "and version-locked environment settings."
            )
    elif category == "Non-determinism":
        root_cause = (
            "Seed and randomness handling changed, introducing non-deterministic behavior so repeated runs no longer follow a "
            "stable evaluation path."
        )
        fix = (
            "Set explicit seed and random_state values across training, splitting, and shuffling steps, and enforce deterministic "
            "execution in the data pipeline before revalidation."
        )
    elif category == "Data drift":
        root_cause = (
            "Data pipeline consistency appears broken, which can shift feature distributions and invalidate baseline comparability."
        )
        fix = (
            "Restore dataset hash parity and lock preprocessing/data-split versions so baseline and current runs consume identical "
            "inputs end-to-end."
        )
    elif category == "Code regression":
        if seed_related or pipeline_related:
            root_cause = (
                "Code-level changes around seed/randomness or data pipeline flow likely modified evaluation conditions, causing drift "
                f"(accuracy delta {accuracy_drop:.4f})."
            )
            fix = (
                "Revert the suspect commit and reapply changes incrementally while preserving seed controls, data pipeline invariants, "
                "and deterministic split configuration."
            )
        else:
            root_cause = (
                "A recent code regression changed experiment behavior enough to break reproducibility against the tagged baseline."
            )
            fix = "Revert to the last known-good revision and validate each subsequent change with the reproducibility gate."

    if not dataset_hash_match and "dataset" not in root_cause.lower():
        root_cause = f"{root_cause} Dataset hash mismatch also indicates potential data-pipeline drift."

    explanation["root_cause"] = root_cause
    explanation["fix"] = fix
    return explanation


def intelligent_fallback_analysis(diff_text: str, metrics: dict) -> dict:
    diff_signals = parse_diff_signals(diff_text)
    context = build_reasoning_context(diff_signals, metrics)

    accuracy_drop = context["metric_shift"]["accuracy_drop"]
    loss_increase = context["metric_shift"]["loss_increase"]
    changes = context["detected_changes"]

    removed_keywords = {c["keyword"] for c in changes if c.get("action") == "removed"}
    changed_keywords = {c["keyword"] for c in changes}

    reasoning_steps: list[str] = []

    reasoning_steps.append(
        f"Parsed git diff signals with keywords: {', '.join(diff_signals.get('detected_keywords', [])) or 'none detected'}."
    )
    reasoning_steps.append(
        f"Observed metric shift: accuracy drop {accuracy_drop:.4f}, loss increase {loss_increase:.4f}, impact={context['impact_level']}."
    )

    category = "Code regression"
    root_cause = "Recent code-level changes correlate with metric drift in experiment outcomes."
    fix = "Revert suspect code changes and rerun the baseline-anchored experiment path."

    if "seed" in removed_keywords and accuracy_drop > 0.05:
        category = "Non-determinism"
        root_cause = (
            "The seed parameter appears removed or altered in a way that destabilizes run-to-run behavior, "
            "which aligns with the observed accuracy degradation."
        )
        fix = "Restore a fixed seed and lock deterministic train/test splitting before rerunning analysis."
        reasoning_steps.append("Detected removal of seed-related control while accuracy drop is significant.")
        reasoning_steps.append("Missing deterministic seed explains unstable model behavior across runs.")
    elif "learning_rate" in changed_keywords and loss_increase > 0:
        category = "Hyperparameter instability"
        root_cause = (
            "Learning-rate related modifications align with the rise in loss, indicating unstable optimization "
            "that degrades generalization quality."
        )
        fix = "Revert learning_rate changes or retune with controlled sweeps and reproducible seeds."
        reasoning_steps.append("Detected learning_rate changes with positive loss increase.")
        reasoning_steps.append("Coupled metric movement indicates hyperparameter sensitivity.")
    elif "batch" in changed_keywords and (accuracy_drop > 0.05 or loss_increase > 0.05):
        category = "Hyperparameter instability"
        root_cause = (
            "Batch-related configuration shifted the optimization profile and produced unstable validation behavior."
        )
        fix = "Restore prior batch settings and evaluate batch-size variants in a controlled sweep."
        reasoning_steps.append("Detected batch-related diff lines with meaningful metric shift.")
    elif any(k in changed_keywords for k in ["shuffle", "random"]) and accuracy_drop > 0.05:
        category = "Non-determinism"
        root_cause = (
            "Randomization/shuffle behavior changed and likely altered data exposure order, causing reproducibility drift."
        )
        fix = "Fix shuffle/random_state controls and preserve deterministic split and ordering assumptions."
        reasoning_steps.append("Detected shuffle/random changes correlated with large accuracy drop.")
    elif accuracy_drop > 0.1:
        category = "Hyperparameter instability"
        root_cause = (
            "Large accuracy collapse without a single obvious trigger suggests unstable hyperparameter interactions "
            "introduced by recent changes."
        )
        fix = "Rollback recent experiment parameter edits and reintroduce changes one-at-a-time with metric gates."
        reasoning_steps.append("High-impact metric shock indicates instability beyond normal variation.")
    elif metrics.get("dataset_hash_match") is False:
        category = "Data drift"
        root_cause = "Dataset identity appears inconsistent with baseline expectations, causing evaluation drift."
        fix = "Restore dataset hash parity with baseline and block execution on hash mismatch."
        reasoning_steps.append("Dataset mismatch signal points to data drift as primary cause.")
    else:
        reasoning_steps.append("No single dominant trigger found; defaulting to code regression hypothesis.")

    confidence = 35
    if category in {"Non-determinism", "Hyperparameter instability"} and accuracy_drop > 0.1:
        confidence = 90
    elif category in {"Non-determinism", "Hyperparameter instability", "Data drift"} and accuracy_drop > 0.05:
        confidence = 82
    elif accuracy_drop > 0.05:
        confidence = 68
    elif accuracy_drop > 0.02:
        confidence = 56
    else:
        confidence = 42

    if loss_increase > 0.1:
        confidence = min(95, confidence + 5)

    reasoning_steps.append(f"Assigned confidence {confidence}% based on signal coherence and impact level.")

    return {
        "root_cause": root_cause,
        "category": category,
        "fix": fix,
        "confidence": confidence,
        "reasoning_steps": reasoning_steps,
        "context": context,
    }


def get_git_diff_insights() -> dict:
    result = run_git(["diff", "HEAD~1", "HEAD"], check=False)
    diff_text = result.stdout.strip()
    if not diff_text:
        return {
            "diff_snippet": "No diff available for HEAD~1..HEAD.",
            "affected_parameters": [],
            "changed_lines": [],
        }

    affected = []
    changed_lines = []
    patterns = [
        "seed",
        "random_state",
        "test_size",
        "n_estimators",
        "max_depth",
        "dataset",
        "accuracy",
    ]

    for line in diff_text.splitlines():
        if line.startswith("+") or line.startswith("-"):
            for key in patterns:
                if key in line and key not in affected:
                    affected.append(key)
            if any(key in line for key in patterns):
                changed_lines.append(line[:220])

    return {
        "diff_snippet": "\n".join(diff_text.splitlines()[:30]),
        "affected_parameters": affected,
        "changed_lines": changed_lines[:8],
    }


def get_git_blame_insights() -> dict:
    result = run_git(["blame", "-L", "1,220", ANALYSIS_TARGET], check=False)
    if result.returncode != 0:
        return {
            "file": ANALYSIS_TARGET,
            "line": 1,
            "change": "Unable to resolve blame metadata for target file.",
            "blame_lines": [],
        }

    lines = result.stdout.splitlines()
    highlights = [
        line for line in lines if any(token in line for token in ["seed", "random_state", "accuracy", "loss"])
    ]
    selected = highlights[:5] if highlights else lines[:5]

    line_num = 1
    if selected:
        parts = selected[0].split()
        for part in parts:
            if part.isdigit():
                line_num = int(part)
                break

    return {
        "file": ANALYSIS_TARGET,
        "line": line_num,
        "change": "Recent edits in experiment execution logic likely altered reproducibility behavior.",
        "blame_lines": selected,
    }


def build_attribution(changes: dict, failure_type: str, blame_info: dict, diff_info: dict) -> dict:
    changed_files = changes.get("changed_files", [])
    file_name = str(blame_info.get("file") or "experiments/current.yaml")
    if changed_files:
        preferred = [f for f in changed_files if f.startswith("experiments/")]
        if not file_name:
            file_name = preferred[0] if preferred else changed_files[0]

    line_number = int(blame_info.get("line") or (8 if "current.yaml" in file_name else 1))
    affected_parameters = diff_info.get("affected_parameters", [])
    affected_text = ", ".join(affected_parameters) if affected_parameters else "seed and metric controls"
    change = (
        f"Detected {failure_type.lower()} linked to updates impacting {affected_text}. "
        "Git blame and recent diff indicate this location is strongly associated with the observed drift."
    )
    return {
        "file": file_name,
        "line": line_number,
        "change": change,
        "blame_lines": blame_info.get("blame_lines", []),
        "changed_lines": diff_info.get("changed_lines", []),
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

    confidence = payload.get("confidence", 70)
    try:
        confidence = int(confidence)
    except (TypeError, ValueError):
        confidence = 70
    confidence = max(0, min(100, confidence))

    steps = payload.get("reasoning_steps", [])
    if not isinstance(steps, list):
        steps = [str(steps)]

    return {
        "root_cause": str(payload["root_cause"]),
        "category": str(payload["category"]),
        "fix": str(payload["fix"]),
        "confidence": confidence,
        "reasoning_steps": [str(step) for step in steps][:8],
    }


def groq_reasoning(comparison: dict, changes: dict, diff_text: str, metrics: dict) -> dict | None:
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
        "with keys root_cause, category, fix, confidence, reasoning_steps.\n\n"
        "Use category from: Non-determinism, Data drift, Code regression, Hyperparameter instability.\n"
        "confidence must be 0-100 integer. reasoning_steps must be a concise list of causal steps.\n\n"
        f"metric_difference: accuracy_diff={comparison.get('accuracy_diff')}, "
        f"loss_diff={comparison.get('loss_diff')}, divergence={comparison.get('divergence')}\\n"
        f"metrics: {json.dumps(metrics)}\n"
        f"simulated_diff: {json.dumps(changes)}\n"
        f"git_diff_excerpt: {diff_text[:1200]}"
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

    baseline = load_yaml(BASELINE_FILE)
    current = load_yaml(CURRENT_FILE)
    comparison = load_yaml(COMPARISON_FILE)
    bisect_result = load_yaml(BISECT_FILE)

    suspected_commit = bisect_result.get("first_bad_commit")
    changes = get_simulated_changes(suspected_commit)
    diff_info = get_git_diff_insights()
    blame_info = get_git_blame_insights()
    metrics = {
        "accuracy_drop": float(comparison.get("accuracy_diff", 0.0)),
        "loss_increase": float(current.get("results", {}).get("loss", 0.0))
        - float(baseline.get("results", {}).get("loss", 0.0)),
        "divergence": bool(comparison.get("divergence", False)),
        "dataset_hash_match": current.get("dataset", {}).get("hash") == baseline.get("dataset", {}).get("hash"),
    }

    diff_text = str(diff_info.get("diff_snippet", ""))

    explanation = None
    reasoning_source = "intelligent-fallback"
    if os.environ.get("GROQ_API_KEY"):
        print("[INFO] Using Groq LLM reasoning")
        explanation = groq_reasoning(comparison, changes, diff_text, metrics)
        if explanation is not None:
            reasoning_source = "groq-llm"

    if explanation is None:
        print("[INFO] Using intelligent fallback reasoning")
        explanation = intelligent_fallback_analysis(diff_text, metrics)

    explanation["category"] = normalize_category(str(explanation.get("category", "Code regression")))
    explanation = enrich_explanation_text(explanation, metrics, current, baseline, diff_text)
    failure_type = explanation["category"]
    attribution = build_attribution(changes, failure_type, blame_info, diff_info)

    payload = {
        "root_cause": {
            "summary": explanation["root_cause"],
            "category": explanation["category"],
            "fix": explanation["fix"],
            "source": reasoning_source,
            "confidence": int(explanation.get("confidence", 70)),
            "reasoning_steps": explanation.get("reasoning_steps", []),
        },
        "llm_explanation": {
            "root_cause": explanation["root_cause"],
            "category": explanation["category"],
            "fix": explanation["fix"],
            "failure_type": failure_type,
            "confidence": int(explanation.get("confidence", 70)),
            "reasoning_steps": explanation.get("reasoning_steps", []),
        },
        "failure_type": failure_type,
        "attribution": attribution,
        "git_intelligence": {
            "diff": diff_info,
            "blame": blame_info,
        },
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
