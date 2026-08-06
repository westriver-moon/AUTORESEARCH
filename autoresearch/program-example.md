---
goal: Improve the declared primary metric through bounded experiment loops.
metric: primary_metric
direction: higher
budget_mode: default
worker_count: 1
keep_threshold: 0.0
stop_conditions:
  - stop after the user-defined budget
mutable_paths:
  - src/**
notes:
  - Keep changes small and measurable.
---

# Generic example program

Establish a baseline, evaluate candidate changes, keep improvements, and record
failed hypotheses without embedding project semantics in the runtime.
