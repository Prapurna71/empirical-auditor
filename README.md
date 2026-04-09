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

Current status:
- agent.yaml valid
- SOUL.md valid
- skills/ valid
- validator warnings: 0

## Hackathon Compliance Checklist

This repository is aligned to hackathon-critical Skills + Rules requirements.

- Skills are declared in agent.yaml and exist as six kebab-case folders under skills/.
- Each skill has valid frontmatter (name + description + allowed-tools) and a concrete executable instruction.
- Rules are codified in RULES.md and enforced by runtime checks:
   - missing seed is blocked
   - missing dataset hash is blocked
   - divergence threshold is enforced at 0.05
   - divergent runs trigger forensic path (bisect, blame, report, PR simulation)
- Identity and policy docs are present and validated:
   - SOUL.md
   - DUTIES.md
   - RULES.md

Enforcement evidence in scripts:
- scripts/run_experiment.py raises policy violation when hyperparameters.seed is missing.
- scripts/compare_results.py raises policy violations for missing seed or dataset hash and applies threshold 0.05.
- scripts/run_agent.py executes adaptive failure workflow when divergence is detected.
- scripts/blame_analysis.py outputs structured root-cause reasoning with confidence and reasoning steps.

## Run With Gitclaw

```bash
gitclaw run .
```

## One-Command Demo

```bash
python scripts/run_agent.py
```

## External Repository Analysis Mode

Use `--repo` to provide the external repository URL directly in the command.

Example:

```bash
python scripts/run_agent.py --repo https://github.com/Prapurna71/ml-research-demo.git
```

## ⚠️ Requirements for External Repos

Best results when repository includes:
- experiment scripts
- YAML-based outputs
- reproducible pipelines

Demo repo provided for guaranteed behavior.

## Demo Flow (External Repo)

1. Set the target repository URL:

```bash
set REPO_URL=https://github.com/Prapurna71/ml-research-demo.git
```

2. Run analysis on that external repository:

```bash
python scripts/run_agent.py --repo https://github.com/Prapurna71/ml-research-demo.git
```

3. Optional: include PR simulation and push to GitHub:

```bash
python scripts/run_agent.py --repo https://github.com/Prapurna71/ml-research-demo.git --create-pr --push
```

The `--push` flag automatically pushes the PR branch (`repro-failure-branch`) to GitHub, creating a real PR.

4. Optional: clean temporary clone after run:

```bash
python scripts/run_agent.py --repo https://github.com/Prapurna71/ml-research-demo.git --cleanup
```

Combine flags:

```bash
python scripts/run_agent.py --repo https://github.com/Prapurna71/ml-research-demo.git --create-pr --push --cleanup
```

This will analyze the external repo, create and push the PR branch, then clean up local workspace.

You can change https://github.com/Prapurna71/ml-research-demo.git to any other public repository and run again to test another project.

Behavior:
- Clones the target repository into a temporary audit workspace.
- Injects agent runtime folders (`scripts/`, `experiments/`, `memory/`).
- Runs the full reproducibility pipeline in the cloned repository.
- Writes the report to `memory/report.md` inside the cloned repository.
- Prints the absolute report path at the end.

Optional PR simulation for external mode:

```bash
python scripts/run_agent.py --repo https://github.com/Prapurna71/ml-research-demo.git --create-pr
```

Optional cleanup after run:

```bash
python scripts/run_agent.py --repo https://github.com/Prapurna71/ml-research-demo.git --cleanup
```

Safety:
- No automatic push is performed.
- PR behavior is simulated only when `--create-pr` is explicitly provided in external mode.

## LLM Reasoning and Fallback

- If `GROQ_API_KEY` is configured, the agent uses LLM reasoning for richer root-cause analysis.
- If no API key is provided, the agent automatically switches to intelligent fallback reasoning.
- Fallback mode is fully supported and produces the same structured outcome fields (root cause, category, fix, confidence, reasoning steps).

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

