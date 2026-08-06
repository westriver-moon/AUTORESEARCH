# Autoresearch v2 Runtime

`autoresearch-v2.ps1` is the single controller for `access-doctor`,
`access-ensure`, `deploy`, `doctor`, `bootstrap`, `inspect`, `apply`,
`baseline`, `run`, `resume`, `status`, `collect`, `stop`, and `sync-best`.

Supporting entrypoints:

- `select-profile.ps1` selects a configured Profile locally.
- `smoke-autoresearch-v2.ps1` runs the explicit program/target CPU smoke flow.
- `guard-autoresearch-mode.ps1` enforces the policy in
  `.codex/research-policy.json`.

## Boundaries

- `lib/config.ps1` loads the public and ignored local configuration.
- `lib/remote_access.ps1` owns Profile resolution, SSH/SCP, tunnels, and proxy
  checks. `access-doctor` verifies SSH and, when required, the HTTP proxy;
  `access-ensure` may start only the configured tunnel helper.
- `lib/autoresearch_v2.ps1` maps controller operations to the remote bridge.
- `remote-bin/` owns remote worker state, worktrees, leases, retention, and
  collection.

The target owns its repository, argv, environment, metric, declared inputs,
artifacts, and optional lease. The command writes a finite numeric
`primary_metric` to `$AR2_RESULTS_DIR/metrics.json`; the runtime does not infer
metrics from stdout or interpret project semantics.
