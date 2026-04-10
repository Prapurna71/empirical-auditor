from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
REPORT_FILE = ROOT / "memory" / "report.md"
AUDIT_LOG = ROOT / "memory" / "audit_log.md"
PR_FILE = ROOT / "memory" / "replication_pr.md"
PR_BRANCH_ENV = "AUDIT_PR_BRANCH"


def run_git(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=check,
    )


def main() -> None:
    if not REPORT_FILE.exists():
        raise FileNotFoundError("Report missing: run scripts/generate_report.py first")

    now = datetime.now(timezone.utc).isoformat()
    branch_name = os.environ.get(PR_BRANCH_ENV, f"repro-failure-{int(time.time())}")

    report_text = REPORT_FILE.read_text(encoding="utf-8")
    title = "Analysis Branch: Reproducibility Failure Investigation"

    pr_text = (
        f"# {title}\n\n"
        f"- Created: {now}\n"
        f"- Source report: memory/report.md\n"
        f"- Status: OPEN (simulated analysis branch)\n"
        f"- Branch: {branch_name}\n"
        "- Target: main\n\n"
        "## Included Artifacts\n\n"
        "- experiments/current.yaml\n"
        "- experiments/comparison.yaml\n"
        "- experiments/bisect_result.yaml\n"
        "- experiments/blame_result.yaml\n"
        "- memory/report.md\n\n"
        "## Report Snapshot\n\n"
        f"{report_text}\n"
    )

    PR_FILE.write_text(pr_text, encoding="utf-8")

    existing = run_git(["branch", "--list", branch_name], check=False).stdout.strip()
    if existing:
        run_git(["checkout", branch_name], check=False)
    else:
        run_git(["checkout", "-b", branch_name], check=True)

    with AUDIT_LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"- {now}: Simulated analysis branch created: {branch_name}.\\n")

    run_git(["add", "memory/report.md", "memory/replication_pr.md", "memory/audit_log.md"], check=False)
    run_git(["commit", "--allow-empty", "-m", "Reproducibility failure report"], check=False)

    print(f"Simulated PR created: {branch_name} -> main (analysis-only, no code changes)")


if __name__ == "__main__":
    main()
