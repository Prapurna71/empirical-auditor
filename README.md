# Empirical Auditor

Machine learning experiments often fail to reproduce.

A small change in code, data loading, or hyperparameters can silently break results - and debugging this can take hours or even days.

Empirical Auditor is a Git-native AI agent that automatically detects reproducibility failures, identifies the exact commit that caused them, and explains why they happened - in seconds.

## How It Works

1. Runs an experiment and compares results with a baseline.
2. Detects divergence beyond the configured threshold.
3. Uses Git history - diff, blame, and bisect - to find the breaking commit.
4. Generates a detailed audit report with root cause and recommended fix.

Instead of manually debugging across commits, logs, and configurations, the agent turns Git into a forensic system for ML experiments.

## Why This Is Useful

This helps ML teams quickly answer the questions that matter most:
- What changed?
- When did it break?
- Why did it break?
- What should we do next?

## What Makes It Unique

- Git-native audit trail: commits become experiment history.
- Root cause analysis, not just failure detection.
- Human-in-the-loop workflow via a PR-ready branch.
- Works locally, in CI, or on external repositories.

## Why This Is an Intelligent Agent

The agent does not follow a fixed pipeline blindly.
It evaluates divergence severity, selects analysis strategies like bisect and blame, and produces causal explanations based on Git evidence and experiment signals.

## Architecture

Empirical Auditor is organized as a Git-driven analysis loop:

1. `scripts/run_agent.py` orchestrates the workflow.
2. `scripts/run_experiment.py` writes current experiment results.
3. `scripts/compare_results.py` compares current results against the baseline.
4. `scripts/decision_engine.py` chooses the next analysis steps.
5. `scripts/bisect_simulation.py` finds the first bad commit.
6. `scripts/blame_analysis.py` explains why the failure happened.
7. `scripts/generate_report.py` writes the audit report.
8. `scripts/create_pr.py` prepares the PR-ready analysis branch.

Git is the memory layer, the audit trail, and the source of truth.

## 🚀 Run in 10 Seconds

```bash
git clone <repo_url>
cd empirical-auditor

pip install -r requirements.txt

python scripts/run_agent.py --demo
```

## What You Will See

- Experiment run and divergence detection
- Agent decision-making process
- Root cause identification using Git
- Reproducibility audit report
- PR-ready branch with analysis

## PR Workflow

The agent creates a PR-ready branch containing:
- reproducibility audit report
- root cause analysis
- recommended fix

No source code is modified automatically. Human review is required.

## External Repository Analysis

The agent can audit any Git repository:

```bash
python scripts/run_agent.py --repo <repo_url>
```

Analysis runs in an isolated environment without modifying the original repository.

## External Demo Repository

For the judge demo, use this repository URL:

```bash
https://github.com/Prapurna71/ml-research-demo.git
```

Run the external-repo analysis with:

```bash
python scripts/run_agent.py --repo https://github.com/Prapurna71/ml-research-demo.git --create-pr --push
```

This produces a PR-ready analysis branch and a reproducibility audit report.

To test a different repository, replace the URL after `--repo`:

```bash
python scripts/run_agent.py --repo <your_repo_url> --create-pr --push
```

You can also use only the analysis mode without PR creation:

```bash
python scripts/run_agent.py --repo <your_repo_url>
```

## Note

This project uses controlled experiment setups to simulate realistic reproducibility failures in ML workflows.

## Modes

- Demo Mode: Controlled reproducibility failure for quick testing.
- Local Mode: Runs on the current repository.
- External Mode: Audits any Git repository in an isolated environment.

## Setup

1. Create and activate the environment:

```bash
conda create -n gitagent-env python=3.11 -y
conda activate gitagent-env
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Configure the optional LLM key:

```bash
copy .env.example .env
```

Set `GROQ_API_KEY` in `.env` for richer reasoning. If no API key is provided, the agent uses intelligent fallback reasoning.

## Validate GitAgent Spec

```bash
npx -y @open-gitagent/gitagent validate
```

## Demo Artifacts

- `experiments/current.yaml`
- `experiments/comparison.yaml`
- `experiments/bisect_result.yaml`
- `experiments/blame_result.yaml`
- `memory/report.md`
- `memory/replication_pr.md`
- `memory/audit_log.md`

## License

See the repository for licensing details.
