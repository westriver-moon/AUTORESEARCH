# Autoresearch v2 Runtime

`autoresearch-v2.ps1` is the single controller for `access-doctor`,
`access-ensure`, `deploy`, `doctor`, `bootstrap`, `inspect`, `apply`,
`baseline`, `run`, `resume`, `status`, `collect`, `stop`, `sync-best`, and
`sync`.
`sync` fetches run branches directly from the selected server repository's git
remote; `-Checkout -CheckoutBranch <branch>` also fetches that exact branch and
updates the local worktree.

Supporting entrypoints:

- `select-profile.ps1` resolves the session Profile. The first call per Codex
  session locks `ActiveRemoteProfile` (or the passed `-RemoteProfile`); later
  calls return the lock. `-Force` overwrites the lock for an explicit switch.
- `smoke-autoresearch-v2.ps1` runs the explicit program/target CPU smoke flow.
- `guard-autoresearch-mode.ps1` enforces the policy in
  `.codex/research-policy.json`.

## Boundaries

- `lib/config.ps1` loads the public and ignored local configuration.
- `lib/profile_session_state.ps1` owns the per-thread Profile lock.
- `lib/remote_access.ps1` owns Profile resolution, SSH/SCP, tunnels, and proxy
  checks. `access-doctor` verifies SSH, expected host/user identity, and, when
  required, the HTTP proxy; `access-ensure` may start only the configured
  tunnel helper.
- `lib/autoresearch_v2.ps1` resolves runtime roots from the selected Profile,
  allowing different accounts or servers to use different home directories.
- `lib/autoresearch_v2.ps1` maps controller operations to the remote bridge.
- `lib/autoresearch_v2.ps1` owns direct server git remote synchronization when
  `LocalRepositoryPath` and `LocalGitRemoteName` are configured.
- `remote-bin/` owns remote worker state, worktrees, leases, retention, and
  collection.

The target owns its repository, argv, environment, metric, declared inputs,
artifacts, and optional lease. The command writes a finite numeric
`primary_metric` to `$AR2_RESULTS_DIR/metrics.json`; the runtime does not infer
metrics from stdout or interpret project semantics.
