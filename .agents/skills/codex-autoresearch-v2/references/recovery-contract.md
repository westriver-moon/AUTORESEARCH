# Recovery Contract

- Worker status is resumable from `state.json`.
- Background runner processes are tracked by PID.
- `resume` only relaunches non-running workers.
- `stop` must release GPU leases before returning.
- A completed, discarded, or failed worker must not retain a PID or GPU assignment in state.
- Process errors, metric errors, and timeouts without a valid metric are persisted as canonical crash outcomes before the error is returned.
- `doctor` fails when any required executable, bridge module, writable runtime root, or provided/retained target repository check fails.
