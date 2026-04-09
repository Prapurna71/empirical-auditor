# Reproducibility Failure Report

## Executive Summary

| Field | Value |
|---|---|
| Status | **FAIL** |
| Generated At | 2026-04-09 18:17:25 UTC |
| Baseline Experiment | exp-iris-baseline |
| Current Experiment | exp-iris-current |
| Divergence Detected | true |
| Reproducibility Score | **75/100** |

## Metric Comparison Table

| Metric | Baseline | Current | Absolute Difference | Threshold |
|---|---:|---:|---:|
| Accuracy | 0.9889 | 0.8100 | 0.1789 | 0.0500 |
| Loss | 0.1162 | 0.5225 | 0.4063 | N/A |

## Reproducibility Score

Reproducibility Score: **75/100**

| Component | Points |
|---|---:|
| Seed Present | 25 |
| Dataset Hash Match | 25 |
| Environment Match | 25 |
| Stable Metrics | 0 |

## Root Cause

Uncommitted changes in experiment configuration files

## Suspected Commit

`0a56ebc`

## Recommended Fix

Commit all changes, especially in experiments/baseline.yaml, experiments/current.yaml, and scripts/run_experiment.py, before running the experiment

## Decision

Reject reproducibility: divergence exceeds threshold.

## Traceability

| Artifact | Value |
|---|---|
| Comparison File | experiments/comparison.yaml |
| Bisect File | experiments/bisect_result.yaml |
| Blame File | experiments/blame_result.yaml |
| Reasoning Source | groq-llm |

## Git Diff

```diff
No diff detected between experiments/baseline.yaml and experiments/current.yaml.
```

