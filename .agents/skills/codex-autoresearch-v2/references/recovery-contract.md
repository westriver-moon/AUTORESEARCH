# Recovery Contract

- Worker status is resumable from `state.json`.
- Background runner processes are tracked by PID.
- `resume` only relaunches non-running workers.
- `stop` must release GPU leases before returning.
