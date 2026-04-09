# Reproducibility Failure Report

## Summary

Baseline Accuracy: **0.9889**

Current Accuracy: **0.8100**

Change: **-0.1789**

Status: **FAIL ❌**

Generated At: 2026-04-09 18:21:43 UTC

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

## Experiment Timeline

- d1b9dba (baseline) -> Accuracy 0.9889 [stable PASS] - pipeline: run completed
- b4f28ad (intermediate) -> Accuracy 0.9789 [stable PASS] - experiment: new run
- 4e8e1a5 (intermediate) -> Accuracy 0.9689 [stable PASS] - analysis: divergence detected
- 40d2ab5 (intermediate) -> Accuracy 0.9589 [stable PASS] - analysis: bisect completed
- d709124 (intermediate) -> Accuracy 0.9589 [stable PASS] - analysis: root cause generated

## Root Cause

Uncommitted changes in experiment configuration files

Suspected Commit: `0a56ebc`

## Failure Classification

Model instability

## Root Cause Attribution

File: `experiments/baseline.yaml`

Line: `1`

Change: Detected model instability linked to configuration updates in this file. Seed/metric related values likely changed relative to baseline expectations.

## Git Diff

```diff
No diff detected between experiments/baseline.yaml and experiments/current.yaml.
```

## Recommended Fix

Commit all changes to configuration files before running the experiment, specifically review changes in experiments/baseline.yaml, experiments/current.yaml, and agent.yaml

