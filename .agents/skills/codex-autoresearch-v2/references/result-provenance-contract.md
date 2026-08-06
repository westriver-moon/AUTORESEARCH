# Result and provenance contract

Each experiment command receives runtime-owned environment variables:

- `AR2_WORKER_ROOT`
- `AR2_RUN_DIR`
- `AR2_OUTPUT_DIR`
- `AR2_RESULTS_DIR`
- `AR2_BUDGET_MINUTES`
- `AR2_GPU_ID` only when a lease was acquired

Write `$AR2_RESULTS_DIR/metrics.json` atomically before returning success:

```json
{
  "primary_metric": 12.5,
  "metrics": {
    "secondary": -3.0
  }
}
```

`primary_metric` is required and finite. Optional `metrics` maps non-empty names
to finite numbers. The runtime neither interprets names nor parses stdout.

In the target, `artifacts` declares collected files and `provenance.inputs`
declares immutable inputs to hash. Both contain paths relative to the worker
repository. Project-specific expansion, parsing, and reporting belong in
`run.argv`.

Recorded provenance covers argv/cwd, program and target hashes, Git state,
declared input and runtime hashes, a redacted environment, exit status, metrics,
and artifact hashes. Core events: `run_started`, `metric_recorded`,
`artifact_recorded`, `run_finished`.
