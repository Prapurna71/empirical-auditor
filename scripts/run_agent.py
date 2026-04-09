from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
AUDIT_LOG = ROOT / "memory" / "audit_log.md"
REPORT_FILE = ROOT / "memory" / "report.md"
COMPARISON_FILE = ROOT / "experiments" / "comparison.yaml"
BASELINE_TAG = "baseline-v1"


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


def run_step(step_label: str, script_name: str, logs: list[str]) -> tuple[int, str, str]:
    command = [sys.executable, str(SCRIPTS_DIR / script_name)]
    display_command = f"python scripts/{script_name}"

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


def fail(logs: list[str], message: str) -> int:
    print(message)
    logs.append(message)
    append_audit_line(message)

    if not REPORT_FILE.exists():
        REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
        REPORT_FILE.write_text(
            "# Reproducibility Failure Report\n\n"
            "Pipeline failed before full report generation.\n",
            encoding="utf-8",
        )

    run_step("[FAILURE-HANDLER]", "create_pr.py", logs)

    logs.append("FINAL_RESULT: FAILURE")
    append_audit_log(logs)
    commit_step("failure: pipeline error logged", ["memory/audit_log.md", "memory/report.md", "memory/replication_pr.md"])
    print("FAILURE")
    return 1


def main() -> int:
    logs: list[str] = [f"PIPELINE_START: {timestamp()}"]
    append_audit_line("Pipeline started")

    ensure_baseline_tag(logs)

    print("[STEP 1] Running experiment")
    logs.append("[STEP 1] Running experiment")
    append_audit_line("Experiment started")
    code, _, _ = run_step("[STEP 1]", "run_experiment.py", logs)
    if code != 0:
        return fail(logs, "[ERROR] Experiment step failed.")
    append_audit_line("Experiment completed")
    commit_step("experiment: new run", ["experiments/current.yaml", "memory/audit_log.md"])

    print("[STEP 2] Detecting divergence")
    logs.append("[STEP 2] Detecting divergence")
    append_audit_line("Divergence detection started")
    code, stdout, _ = run_step("[STEP 2]", "compare_results.py", logs)
    if code != 0:
        return fail(logs, "[ERROR] Divergence check failed.")

    divergence = read_divergence_from_file()
    if divergence is None:
        divergence = extract_divergence(stdout)
    if divergence is None:
        return fail(logs, "[ERROR] Could not parse divergence output from compare_results.py")

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
        print("SUCCESS")
        return 0

    print("[STEP 3] Running bisect simulation")
    logs.append("[STEP 3] Running bisect simulation")
    append_audit_line("Bisect simulation started")
    code, _, _ = run_step("[STEP 3]", "bisect_simulation.py", logs)
    if code != 0:
        return fail(logs, "[ERROR] Bisect simulation failed.")
    append_audit_line("Bisect completed")
    commit_step("analysis: bisect completed", ["experiments/bisect_result.yaml", "memory/audit_log.md"])

    print("[STEP 4] Running blame analysis")
    logs.append("[STEP 4] Running blame analysis")
    append_audit_line("Root cause analysis started")
    code, _, _ = run_step("[STEP 4]", "blame_analysis.py", logs)
    if code != 0:
        return fail(logs, "[ERROR] Blame analysis failed.")
    append_audit_line("Root cause analysis completed")
    commit_step("analysis: root cause generated", ["experiments/blame_result.yaml", "memory/audit_log.md"])

    print("[STEP 5] Generating report")
    logs.append("[STEP 5] Generating report")
    append_audit_line("Report generation started")
    code, _, _ = run_step("[STEP 5]", "generate_report.py", logs)
    if code != 0:
        return fail(logs, "[ERROR] Report generation failed.")
    append_audit_line("Report generated")
    commit_step("report: reproducibility failure", ["memory/report.md", "memory/audit_log.md"])

    print("[STEP 6] Creating replication PR")
    logs.append("[STEP 6] Creating replication PR")
    append_audit_line("PR simulation started")
    code, _, _ = run_step("[STEP 6]", "create_pr.py", logs)
    if code != 0:
        return fail(logs, "[ERROR] PR creation simulation failed.")
    append_audit_line("PR simulation completed")

    logs.append("FINAL_RESULT: SUCCESS")
    logs.append(f"PIPELINE_END: {timestamp()}")
    append_audit_log(logs)
    commit_step("pipeline: run completed", ["memory/audit_log.md", "memory/replication_pr.md"])
    print("SUCCESS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
