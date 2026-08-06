# Runtime State Contract

## Retention

- A run has one baseline; reject attempts to replace it.
- Keep only a strict improvement beyond `keep_threshold`.
- Reset discarded/crashed workers to the retained best commit.
- Treat a timeout with a valid metric like any other completed trial.
- Record one append-only canonical outcome per `trial_id` across all views.
- Record crashes without a metric or delta and reject pre-v2 result headers.

## Recovery

- Resume worker state from `state.json` and relaunch only stopped workers.
- Track workers by PID; clear PID/GPU state after completion, crash, or discard.
- Release GPU leases on stop.
- Persist process, metric, and metric-less timeout failures before returning.
- `doctor` fails any required executable, module, writable-root, or repository
  check.

## Parallel workers

- Give each worker an independent branch and worktree.
- Update the best branch only after a retained improvement.
- Let workers sync to the retained best commit.
- Share one ledger and leaderboard.
