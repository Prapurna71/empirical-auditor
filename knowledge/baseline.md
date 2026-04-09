# Baseline Reference

Baseline experiment `exp-iris-baseline` is treated as the stable reference point.

Reference assumptions:
- Dataset: Iris
- Dataset hash: immutable fingerprint of sklearn Iris features and labels
- Python runtime: 3.11
- Seed: deterministic and recorded

Interpretation rules:
- Accuracy drift greater than 0.05 is a reproducibility failure.
- Loss increases alongside accuracy drop strengthen divergence confidence.
- Missing seed or dataset hash is a hard policy violation.
