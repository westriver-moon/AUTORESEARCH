# Keep / Discard Contract

- A baseline is the first retained measured result.
- A run has exactly one baseline. A second or concurrent baseline attempt is rejected before it can replace retained state.
- A keep requires a strict improvement beyond `keep_threshold`.
- A discard resets the worker branch back to the retained best commit.
- A timeout is a completion reason, not automatically a failed trial. If its metric is valid, it follows the same keep/discard decision path as a normally completed process.
- Every started trial has one canonical outcome keyed by `trial_id`. That outcome feeds `outcome.json`, `results.tsv`, `events.jsonl`, and the correlated worker state fields.
- Failed trials use `decision=crash`; their metric and delta are empty, and their worktree is reset to the retained best commit when possible.
- Results logging is append-only and idempotent by `trial_id`.
- The results schema includes `trial_id`, `completion_reason`, `process_exit_code`, `metric_extracted`, `error_type`, and `timed_out`. A pre-v2 header is rejected explicitly and must be archived or migrated before the run continues.
