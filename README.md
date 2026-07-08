# Research Remote Operations

This repository now treats `scripts/remote/autoresearch-v2.ps1` as the primary
autoresearch runtime.

## Primary Entry Points

```text
scripts/remote/autoresearch-v2.ps1
  Remote-first controller for deploy / doctor / bootstrap / inspect / apply /
  baseline / run / resume / status / collect / stop / sync-best.

scripts/remote/smoke-autoresearch-v2.ps1
  Non-GPU smoke workflow against the real server git layout.

scripts/remote/doctor.ps1
  Read-only SSH / proxy / fixed-entry health check for the remote host.

scripts/remote/ensure-connectivity.ps1
  Starts the local tunnel helper when needed, then checks SSH and proxy status.
```

## Manual Utilities

The following scripts remain for manual preflight or human-confirmed training
outside the autonomous loop:

```text
scripts/remote/submit-smoke-test.ps1
scripts/remote/submit-job.ps1
scripts/remote/check-job.ps1
scripts/remote/fetch-results.ps1
scripts/remote/cancel-own-job.ps1
scripts/remote/sync-code.ps1
```

`submit-job.ps1 -ConfirmFullTraining` remains the explicit boundary for full
training.

## v2 Inputs

```text
autoresearch/program.md
autoresearch/targets/*.yaml
config/autoresearch-v2.example.psd1
config/remote.local.psd1
```

The default Stage A target assumes:

- remote git root: `/home/cgv841/ybj`
- active training subproject: `TVI-LFM/`
- remote controller root: `/home/cgv841/ybj/autoresearch-v2`

## Skill State

The active project-local invocation skill is:

```text
.agents/skills/codex-autoresearch-v2/
```

Development of the skill/runtime uses a separate skill:

```text
.agents/skills/codex-autoresearch-v2-dev/
```

Invocation mode treats the v2 skill, runtime, guard, and package as sealed
implementation code. Check that boundary with:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\remote\guard-autoresearch-mode.ps1 -Mode invoke -FromGit -Json
```

The repo pre-commit hook uses the same guard. Invocation mode is the default;
implementation commits should opt into development mode:

```powershell
$env:AUTORESEARCH_MODE = 'develop'
git commit
```

The versioned repo-local plugin package is:

```text
plugins/codex-autoresearch-v2/
```

## Typical Flow

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\remote\doctor.ps1 -Json
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\remote\autoresearch-v2.ps1 -Mode deploy -RunTag doctor -Json
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\remote\autoresearch-v2.ps1 -Mode bootstrap -RunTag <run-tag> -Json
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\remote\autoresearch-v2.ps1 -Mode inspect -RunTag <run-tag> -Worker w1 -Json
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\remote\autoresearch-v2.ps1 -Mode apply -RunTag <run-tag> -Worker w1 -SourcePath <path> -Json
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\remote\autoresearch-v2.ps1 -Mode baseline -RunTag <run-tag> -Worker w1 -Json
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\remote\autoresearch-v2.ps1 -Mode run -RunTag <run-tag> -AllWorkers -Json
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\remote\autoresearch-v2.ps1 -Mode status -RunTag <run-tag> -Json
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\remote\autoresearch-v2.ps1 -Mode collect -RunTag <run-tag> -Json
```
