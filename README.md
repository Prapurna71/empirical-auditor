# Empirical Auditor - Scientific Reproducibility Agent

Empirical Auditor is a Git-native AI agent for detecting ML reproducibility failures with auditable, file-based evidence.

## Problem

Machine learning teams often cannot reliably reproduce historical results. Missing seeds, undocumented data changes, or untracked environment drift can make previous metrics impossible to validate. This is a practical form of the reproducibility crisis.

## Solution

Empirical Auditor treats Git as a scientific ledger:
- experiment manifests are stored as versioned YAML
- experiments are re-run from scriptable procedures
- baseline and current metrics are compared against a strict divergence threshold
- root cause is localized via simulated bisect and blame workflows
- a structured markdown report and replication PR artifact are produced

## Architecture Flow Diagram

[Git YAML Experiments] -> [run_experiment.py] -> [compare_results.py]
       -> if divergence -> [bisect_simulation.py] -> [blame_analysis.py]
       -> [generate_report.py] -> [create_pr.py]
       -> [memory/report.md + memory/replication_pr.md]

## Repository Structure

- agent metadata: `agent.yaml`, `SOUL.md`, `RULES.md`, `DUTIES.md`
- experiment manifests: `experiments/baseline.yaml`, `experiments/current.yaml`
- execution scripts: `scripts/*.py`
- skills: `skills/*/SKILL.md`
- outputs: `memory/audit_log.md`, `memory/report.md`, `memory/replication_pr.md`

## Local Setup

1. Create and activate conda environment:

   ```bash
   conda create -n gitagent-env python=3.11 -y
   conda activate gitagent-env
   ```

2. Install dependencies:

   ```bash
   pip install pyyaml scikit-learn
   ```

## Validate Gitagent Spec

Run:

```bash
npx gitagent validate
```

## Run With Gitclaw

Run the agent repository with gitclaw from this directory:

```bash
gitclaw run .
```

If your gitclaw version expects an explicit agent file, use:

```bash
gitclaw run --agent agent.yaml .
```

## Demo Steps

1. Ensure divergence scenario by changing seed in `experiments/current.yaml` to a different value than baseline.
2. Re-run the experiment:

   ```bash
   python scripts/run_experiment.py
   ```

3. Detect divergence:

   ```bash
   python scripts/compare_results.py
   ```

4. If divergence is true, run full audit pipeline:

   ```bash
   python scripts/bisect_simulation.py
   python scripts/blame_analysis.py
   python scripts/generate_report.py
   python scripts/create_pr.py
   ```

## Example Output

```text
Experiment re-run complete: seed=12, accuracy=0.9222, loss=2.8153
divergence=true
accuracy_diff=0.0667 threshold=0.05 loss_diff=2.6991
first_bad_commit=d4e5f6g
PR CREATED
```

Generated artifacts:
- `experiments/comparison.yaml`
- `experiments/bisect_result.yaml`
- `experiments/blame_result.yaml`
- `memory/report.md`
- `memory/replication_pr.md`
