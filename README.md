# Empirical Auditor - Scientific Reproducibility Agent

Empirical Auditor is a fully Git-native AI agent that treats Git history as the source of truth for ML reproducibility decisions.

## Why This Matters

The reproducibility crisis in ML happens when teams cannot answer simple questions with evidence:
- Which exact experiment configuration produced the reported metric?
- When did the drift start?
- What change introduced the failure?

Empirical Auditor addresses this by converting every stage of the audit process into versioned Git artifacts and commits.

## Git-Native Core

Git is used as the runtime memory and audit database:
- Every pipeline step writes files and creates a commit.
- Baseline comparisons use a Git tag (`baseline-v1`).
- Divergence analysis uses `git log`, `git checkout`, and commit-level replay.
- Reports include real `git diff` evidence.
- Failure handling creates a PR branch simulation.

## Architecture Diagram (Text)

```
python scripts/run_agent.py
  -> [Step 1] run_experiment.py
     -> commit: experiment: new run
  -> [Step 2] compare_results.py
     -> baseline source: git show baseline-v1:experiments/baseline.yaml
     -> commit: analysis: divergence detected / analysis: no divergence
  -> if divergence:
     -> [Step 3] bisect_simulation.py
        -> commit: analysis: bisect completed
     -> [Step 4] blame_analysis.py (Groq + fallback)
        -> commit: analysis: root cause generated
     -> [Step 5] generate_report.py (includes Git diff)
        -> commit: report: reproducibility failure
     -> [Step 6] create_pr.py
        -> branch: repro-failure-branch
        -> commit: Reproducibility failure report
```

## Setup

1. Create and activate environment:

```bash
conda create -n gitagent-env python=3.11 -y
conda activate gitagent-env
```

2. Install dependencies:

```bash
pip install pyyaml scikit-learn groq
```

3. Configure LLM key (optional but recommended):

```bash
copy .env.example .env
```

Set `GROQ_API_KEY` in `.env`.

## Validate Gitagent Spec

```bash
npx -y @open-gitagent/gitagent validate
```

## Run With Gitclaw

```bash
gitclaw run .
```

## One-Command Demo

```bash
python scripts/run_agent.py
```

What this command does:
- Runs experiment and commits results.
- Compares against baseline from Git tag.
- Detects divergence and stops early if stable.
- If divergent, runs bisect + root cause reasoning + report + PR branch simulation.
- Appends live logs to `memory/audit_log.md`.

## Sample Output

```text
[STEP 1] Running experiment
[STEP 2] Detecting divergence
divergence=true
[STEP 3] Running bisect simulation
first_bad_commit=<hash>
[STEP 4] Running blame analysis
[STEP 5] Generating report
[STEP 6] Creating replication PR
Simulated PR created: repro-failure-branch -> main
SUCCESS
```

## Demo Artifacts

- `experiments/current.yaml`
- `experiments/comparison.yaml`
- `experiments/bisect_result.yaml`
- `experiments/blame_result.yaml`
- `memory/report.md`
- `memory/replication_pr.md`
- `memory/audit_log.md`

## Why This Wins Hackathons

- Strong visual story: each step is visible in Git commits.
- Deterministic demo path: seed-driven divergence simulation.
- Real debugging narrative: diff + bisect + root-cause explanation.
- End-to-end automation from run to PR simulation in one command.
