from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
AUDIT_LOG = ROOT / "memory" / "audit_log.md"
REPORT_FILE = ROOT / "memory" / "report.md"
COMPARISON_FILE = ROOT / "experiments" / "comparison.yaml"
BASELINE_TAG = "baseline-v1"
DECISION_FILE = ROOT / "experiments" / "decision.yaml"
BLAME_FILE = ROOT / "experiments" / "blame_result.yaml"
EXTERNAL_MODE_ENV = "AUDIT_EXTERNAL_MODE"


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_git(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=check,
    )


def append_audit_line(message: str) -> None:
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"- {timestamp()}: {message}\n")


def commit_step(message: str, paths: list[str]) -> None:
    run_git(["add", *paths], check=False)
    run_git(["commit", "--allow-empty", "-m", message], check=False)


def ensure_baseline_tag(logs: list[str]) -> None:
    tag_exists = run_git(["tag", "--list", BASELINE_TAG], check=False).stdout.strip() == BASELINE_TAG
    if tag_exists:
        logs.append(f"BASELINE_TAG_EXISTS: {BASELINE_TAG}")
        append_audit_line(f"Baseline tag already exists: {BASELINE_TAG}")
        return

    run_git(["tag", BASELINE_TAG], check=False)
    logs.append(f"BASELINE_TAG_CREATED: {BASELINE_TAG}")
    append_audit_line(f"Created baseline tag: {BASELINE_TAG}")


def read_divergence_from_file() -> bool | None:
    if not COMPARISON_FILE.exists():
        return None
    data = yaml.safe_load(COMPARISON_FILE.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return None
    return bool(data.get("divergence", False))


def write_decision(decision: dict) -> None:
    DECISION_FILE.write_text(yaml.safe_dump(decision, sort_keys=False), encoding="utf-8")


def read_blame_failure_type() -> str | None:
    if not BLAME_FILE.exists():
        return None
    data = yaml.safe_load(BLAME_FILE.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return None
    value = data.get("failure_type")
    return str(value) if value else None


def add_learning_pattern(failure_type: str) -> None:
    patterns = {
        "Non-determinism": "Learned pattern: removing seed causes instability.",
        "Data drift": "Learned pattern: dataset hash mismatch is a strong drift indicator.",
        "Code regression": "Learned pattern: code-level parameter edits can silently break reproducibility.",
        "Hyperparameter instability": "Learned pattern: large metric drops often trace back to hyperparameter shifts.",
    }
    message = patterns.get(failure_type, f"Learned pattern: observed failure type {failure_type}.")
    append_audit_line(message)


def run_step(
    step_label: str,
    script_name: str,
    logs: list[str],
    extra_args: list[str] | None = None,
) -> tuple[int, str, str]:
    command = [sys.executable, str(SCRIPTS_DIR / script_name)]
    if extra_args:
        command.extend(extra_args)
    display_command = f"python scripts/{script_name}"
    if extra_args:
        display_command = f"{display_command} {' '.join(extra_args)}"

    print(f"{step_label} {display_command}")
    logs.append(f"{timestamp()} {step_label} {display_command}")

    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()

    if stdout:
        print(stdout)
        logs.append(f"STDOUT:\n{stdout}")
    if stderr:
        print(stderr)
        logs.append(f"STDERR:\n{stderr}")

    logs.append(f"EXIT_CODE: {completed.returncode}")
    return completed.returncode, stdout, stderr


def extract_divergence(stdout: str) -> bool | None:
    match = re.search(r"divergence=(true|false)", stdout)
    if not match:
        return None
    return match.group(1) == "true"


def append_audit_log(logs: list[str]) -> None:
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG.open("a", encoding="utf-8") as handle:
        handle.write("\n## Pipeline Run\n\n")
        for line in logs:
            handle.write(f"- {line}\n")


def fail(logs: list[str], message: str, pr_enabled: bool = True) -> int:
    print(message)
    logs.append(message)
    append_audit_line(message)

    if not REPORT_FILE.exists():
        REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
        REPORT_FILE.write_text(
            "# Reproducibility Audit Report\n\n"
            "Pipeline failed before full report generation.\n",
            encoding="utf-8",
        )

    if pr_enabled:
        run_step("[FAILURE-HANDLER]", "create_pr.py", logs)

    logs.append("FINAL_RESULT: FAILURE")
    append_audit_log(logs)
    commit_step("failure: pipeline error logged", ["memory/audit_log.md", "memory/report.md", "memory/replication_pr.md"])
    print("FAILURE")
    return 1


def run_decision_engine(logs: list[str], demo: bool) -> dict | None:
    args = ["--demo"] if demo else None
    code, stdout, _ = run_step("[DECISION]", "decision_engine.py", logs, extra_args=args)
    if code != 0:
        return None

    text = stdout.strip()
    if not text:
        return None
    last_line = text.splitlines()[-1]
    try:
        return json.loads(last_line)
    except json.JSONDecodeError:
        return None


def read_yaml_if_exists(path: Path) -> dict:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return data
    return {}


def print_final_verdict(divergence: bool, branch_created: bool) -> None:
    baseline = read_yaml_if_exists(ROOT / "experiments" / "baseline.yaml")
    current = read_yaml_if_exists(ROOT / "experiments" / "current.yaml")
    blame = read_yaml_if_exists(BLAME_FILE)

    baseline_acc = float(baseline.get("results", {}).get("accuracy", 0.0))
    current_acc = float(current.get("results", {}).get("accuracy", 0.0))
    root_cause = str(blame.get("root_cause", {}).get("summary", "No root cause identified."))
    recommended_fix = str(blame.get("root_cause", {}).get("fix", "No fix recommendation available."))

    print("====================================")
    print("FINAL VERDICT")
    print("=============")
    print("")
    if divergence:
        print("Status: ❌ REPRODUCIBILITY FAILURE DETECTED")
        print("")
        print(f"Baseline Accuracy: {baseline_acc:.4f}")
        print(f"Current Accuracy: {current_acc:.4f}")
        print("")
        print(f"Root Cause: {root_cause}")
        print("")
        print(f"Recommended Fix: {recommended_fix}")
        print("")
        print("Report Location:")
        print("memory/report.md")
        print("")
        print("Branch:")
        print("repro-failure-branch (created)" if branch_created else "Not created (PR disabled)")
    else:
        print("Status: ✅ REPRODUCIBLE")
        print("")
        print(f"Baseline Accuracy: {baseline_acc:.4f}")
        print(f"Current Accuracy: {current_acc:.4f}")
        print("")
        print("Report Location:")
        print("memory/report.md")
    print("")
    print("====================================")


def copy_agent_runtime(target_root: Path) -> None:
    required_paths = ["scripts", "experiments", "memory"]
    for rel_path in required_paths:
        src = ROOT / rel_path
        dst = target_root / rel_path
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)


def run_external_repo_mode(repo_url: str, create_pr: bool, push: bool, cleanup: bool) -> int:
    if os.name == "nt":
        repo_root = Path(tempfile.gettempdir()) / "audit_repo"
    else:
        repo_root = Path("/tmp") / "audit_repo"

    if repo_root.exists():
        shutil.rmtree(repo_root)
    repo_root.parent.mkdir(parents=True, exist_ok=True)

    sidecar_root = repo_root / ".empirical-auditor"

    print("[INFO] Cloning repository")
    clone_result = subprocess.run(
        ["git", "clone", repo_url, "audit_repo"],
        cwd=repo_root.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    if clone_result.returncode != 0:
        if clone_result.stdout.strip():
            print(clone_result.stdout.strip())
        if clone_result.stderr.strip():
            print(clone_result.stderr.strip())
        print("[ERROR] Failed to clone external repository")
        return clone_result.returncode

    copy_agent_runtime(sidecar_root)

    print("[INFO] Running audit on external repo")
    print("[INFO] Using isolated sidecar environment: .empirical-auditor/")
    command = [sys.executable, str(sidecar_root / "scripts" / "run_agent.py")]
    if create_pr:
        command.append("--create-pr")

    env = os.environ.copy()
    env[EXTERNAL_MODE_ENV] = "1"

    result = subprocess.run(
        command,
        cwd=sidecar_root,
        check=False,
        env=env,
    )

    report_path = sidecar_root / "memory" / "report.md"
    if report_path.exists():
        print(f"[INFO] Report path: {report_path}")

    if create_pr and push:
        print("[INFO] Pushing PR branch to GitHub")
        push_result = subprocess.run(
            ["git", "push", "origin", "repro-failure-branch"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if push_result.returncode == 0:
            print("[SUCCESS] PR branch pushed to origin")
        else:
            if push_result.stdout.strip():
                print(push_result.stdout.strip())
            if push_result.stderr.strip():
                print("[WARNING] Push failed:", push_result.stderr.strip())

    if cleanup:
        shutil.rmtree(repo_root, ignore_errors=True)
        print("[INFO] Cleaned up external repository workspace")

    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run adaptive Git-native reproducibility agent")
    parser.add_argument("--demo", action="store_true", help="Force visible divergence demo mode")
    parser.add_argument("--repo", type=str, default=None, help="Analyze an external git repository URL")
    parser.add_argument("--create-pr", action="store_true", help="Enable PR simulation for external-repo mode")
    parser.add_argument("--push", action="store_true", help="Push PR branch to GitHub (requires --create-pr)")
    parser.add_argument("--cleanup", action="store_true", help="Delete cloned external repo after run")
    args = parser.parse_args()

    external_mode = os.environ.get(EXTERNAL_MODE_ENV) == "1"
    if args.repo and not external_mode:
        return run_external_repo_mode(args.repo, args.create_pr, args.push, args.cleanup)

    pr_enabled = (not external_mode) or args.create_pr

    logs: list[str] = [f"PIPELINE_START: {timestamp()}"]
    append_audit_line("Pipeline started")

    ensure_baseline_tag(logs)

    print("[STEP 1] Running experiment")
    logs.append("[STEP 1] Running experiment")
    append_audit_line("Experiment started")
    run_args = ["--seed", "7"] if args.demo else None
    if args.demo:
        append_audit_line("Demo mode enabled: forcing seed=7 for visible divergence")
    code, _, _ = run_step("[STEP 1]", "run_experiment.py", logs, extra_args=run_args)
    if code != 0:
        return fail(logs, "[ERROR] Experiment step failed.", pr_enabled=pr_enabled)
    append_audit_line("Experiment completed")
    commit_step("experiment: new run", ["experiments/current.yaml", "memory/audit_log.md"])

    print("[STEP 2] Detecting divergence")
    logs.append("[STEP 2] Detecting divergence")
    append_audit_line("Divergence detection started")
    code, stdout, _ = run_step("[STEP 2]", "compare_results.py", logs)
    if code != 0:
        return fail(logs, "[ERROR] Divergence check failed.", pr_enabled=pr_enabled)

    divergence = read_divergence_from_file()
    if divergence is None:
        divergence = extract_divergence(stdout)
    if divergence is None:
        return fail(logs, "[ERROR] Could not parse divergence output from compare_results.py", pr_enabled=pr_enabled)

    append_audit_line(f"Divergence detected={divergence}")
    commit_step("analysis: divergence detected", ["experiments/comparison.yaml", "memory/audit_log.md"])

    if not divergence:
        message = "[INFO] No divergence detected. Stopping pipeline after step 2."
        print(message)
        logs.append(message)
        append_audit_line("Pipeline stopped: no divergence")
        logs.append("FINAL_RESULT: SUCCESS")
        append_audit_log(logs)
        commit_step("analysis: no divergence", ["memory/audit_log.md"])
        print_final_verdict(divergence=False, branch_created=False)
        print("SUCCESS")
        return 0

    decision = run_decision_engine(logs, args.demo)
    if decision is None:
        return fail(logs, "[ERROR] Decision engine failed to produce valid output.", pr_enabled=pr_enabled)

    write_decision(decision)
    severity = str(decision.get("severity", "unknown")).lower()
    actions = decision.get("actions", []) if isinstance(decision.get("actions"), list) else []
    action_text = " + ".join([str(action) for action in actions]) if actions else "none"
    print("[AGENT] Decision Summary:")
    print(f"* Severity: {severity}")
    print(f"* Actions: {actions}")
    if severity == "high":
        print(f"[AGENT] Decision: High severity detected -> running {action_text} with Git evidence")
    elif severity == "medium":
        print(f"[AGENT] Decision: Medium severity detected -> running {action_text} with targeted analysis")
    else:
        print(f"[AGENT] Decision: Low severity detected -> running {action_text} with minimal audit path")
    append_audit_line(
        f"Decision engine: severity={decision.get('severity')} actions={decision.get('actions')}"
    )
    commit_step("analysis: adaptive decision computed", ["experiments/decision.yaml", "memory/audit_log.md"])

    actions = decision.get("actions", []) if isinstance(decision, dict) else []
    if not isinstance(actions, list):
        actions = []
    branch_created = False

    if "bisect" in actions:
        print("[STEP 3] Running bisect simulation")
        logs.append("[STEP 3] Running bisect simulation")
        append_audit_line("Bisect simulation started")
        code, _, _ = run_step("[STEP 3]", "bisect_simulation.py", logs)
        if code != 0:
            return fail(logs, "[ERROR] Bisect simulation failed.", pr_enabled=pr_enabled)
        append_audit_line("Bisect completed")
        commit_step("analysis: bisect completed", ["experiments/bisect_result.yaml", "memory/audit_log.md"])
    else:
        append_audit_line("Decision engine skipped bisect for this run")

    if "blame" in actions:
        print("[STEP 4] Running blame analysis")
        logs.append("[STEP 4] Running blame analysis")
        append_audit_line("Root cause analysis started")
        code, _, _ = run_step("[STEP 4]", "blame_analysis.py", logs)
        if code != 0:
            return fail(logs, "[ERROR] Blame analysis failed.", pr_enabled=pr_enabled)
        append_audit_line("Root cause analysis completed")

        failure_type = read_blame_failure_type()
        if failure_type:
            add_learning_pattern(failure_type)

        commit_step("analysis: root cause generated", ["experiments/blame_result.yaml", "memory/audit_log.md"])
    else:
        append_audit_line("Decision engine skipped blame analysis for this run")

    if "report" in actions:
        print("[STEP 5] Generating report")
        logs.append("[STEP 5] Generating report")
        append_audit_line("Report generation started")
        code, _, _ = run_step("[STEP 5]", "generate_report.py", logs)
        if code != 0:
            return fail(logs, "[ERROR] Report generation failed.", pr_enabled=pr_enabled)
        append_audit_line("Report generated")
        commit_step("report: reproducibility failure", ["memory/report.md", "memory/audit_log.md"])
    else:
        append_audit_line("Decision engine skipped report generation for this run")

    if "pr" in actions and pr_enabled:
        branch_created = True
        print("[STEP 6] Creating analysis branch for human review")
        logs.append("[STEP 6] Creating analysis branch for human review")
        append_audit_line("PR simulation started")
        code, _, _ = run_step("[STEP 6]", "create_pr.py", logs)
        if code != 0:
            return fail(logs, "[ERROR] PR creation simulation failed.", pr_enabled=pr_enabled)
        append_audit_line("PR simulation completed")
    elif "pr" in actions and not pr_enabled:
        append_audit_line("PR simulation skipped: external mode without --create-pr")
    else:
        append_audit_line("Decision engine skipped PR simulation for this run")

    logs.append("FINAL_RESULT: SUCCESS")
    logs.append(f"PIPELINE_END: {timestamp()}")
    append_audit_log(logs)
    commit_step("pipeline: run completed", ["memory/audit_log.md", "memory/replication_pr.md"])
    print_final_verdict(divergence=True, branch_created=branch_created)
    print("SUCCESS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
