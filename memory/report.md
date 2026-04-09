# Reproducibility Audit Report

## Summary

- Baseline experiment: exp-iris-baseline
- Current experiment: exp-iris-current
- Divergence detected: true
- Reproducibility score: 70/100

## Metrics Comparison

| Metric | Baseline | Current | Absolute Difference |
|---|---:|---:|---:|
| Accuracy | 0.9889 | 0.9222 | 0.0667 |
| Loss | 0.1162 | 2.8153 | 2.6991 |

## Root Cause Analysis

- Root cause: Recorded seed differs from baseline behavior and introduced measurable metric divergence.
- Suspected commit: d4e5f6g

## Decision

Reject reproducibility: divergence exceeds threshold.
