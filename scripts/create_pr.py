from datetime import datetime, timezone
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REPORT_FILE = ROOT / "memory" / "report.md"
AUDIT_LOG = ROOT / "memory" / "audit_log.md"
PR_FILE = ROOT / "memory" / "replication_pr.md"
PR_BRANCH = "repro-failure-branch"


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

    report_text = REPORT_FILE.read_text(encoding="utf-8")
    title = "Replication PR: Reproducibility Failure Investigation"

    pr_text = (
        f"# {title}\n\n"
        f"- Created: {now}\n"
        f"- Source report: memory/report.md\n"
        f"- Status: OPEN (simulated)\n"
        f"- Branch: {PR_BRANCH}\n"
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

    existing = run_git(["branch", "--list", PR_BRANCH], check=False).stdout.strip()
    if existing:
        run_git(["checkout", PR_BRANCH], check=False)
    else:
        run_git(["checkout", "-b", PR_BRANCH], check=True)

    with AUDIT_LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"- {now}: Simulated replication PR created.\\n")

    run_git(["add", "memory/report.md", "memory/replication_pr.md", "memory/audit_log.md"], check=False)
    run_git(["commit", "--allow-empty", "-m", "Reproducibility failure report"], check=False)

    print("Simulated PR created: repro-failure-branch -> main")


if __name__ == "__main__":
    main()
