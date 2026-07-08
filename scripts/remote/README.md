# Remote Script Contract

This directory exposes the supported local entrypoints for server-side research
automation.

## v2 Runtime

```text
autoresearch-v2.ps1
  Remote-first controller for:
  deploy, doctor, bootstrap, inspect, apply, baseline, run, resume,
  status, collect, stop, sync-best

guard-autoresearch-mode.ps1
  Checks invoke/develop mode boundaries for sealed autoresearch v2 files.

smoke-autoresearch-v2.ps1
  Real-server, non-GPU smoke workflow using the actual git root layout.
```

`autoresearch-v2.ps1` is the only supported autonomous autoresearch runtime in
this repository.

## Manual Operations

```text
doctor.ps1               Read-only SSH / proxy / remote-entry health check.
ensure-connectivity.ps1  Starts the local tunnel helper when needed.
submit-smoke-test.ps1    Fixed remote smoke / preflight entrypoint.
submit-job.ps1           Human-confirmed full training entrypoint.
check-job.ps1            Reads fixed remote status for manual jobs.
fetch-results.ps1        Fetches approved result files for manual jobs.
cancel-own-job.ps1       Cancels only the job matching the experiment id.
sync-code.ps1            Copies a local project path into the remote workspace.
```

## Runtime Files

```text
lib/common.ps1
lib/ssh.ps1
lib/result.ps1
lib/training.ps1
lib/autoresearch_v2.ps1

remote-bin/autoresearch_v2_driver.py
remote-bin/autoresearch_v2_common.py
remote-bin/autoresearch_v2_gpu_lease.py
remote-bin/autoresearch_v2_metric_tvilfm.py
remote-bin/autoresearch_v2_mode_guard.py
remote-bin/run_autoresearch_v2_bridge.sh
```

## Mode Boundary

Use `$codex-autoresearch-v2` for invocation-only work. Use
`$codex-autoresearch-v2-dev` for implementation changes. The authoritative
policy is `.codex/research-policy.json`.

## Remote Layout Assumption

The default v2 target assumes:

- remote git root: `/home/cgv841/ybj`
- active training code: `TVI-LFM/`
- remote controller root: `/home/cgv841/ybj/autoresearch-v2`
