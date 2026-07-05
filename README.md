# Research Remote Operations

This project keeps remote GPU operations behind fixed PowerShell entrypoints.
The tracked files are safe templates; machine-specific host aliases, remote
user paths, SSH settings, and API keys should live only in ignored local config
files.

- Windows PowerShell 5.1 on the local workstation.
- OpenSSH from `C:\Windows\System32\OpenSSH`.
- SSH host alias configured in `config/remote.local.psd1`.
- Optional tunnel alias configured in `config/remote.local.psd1`.
- Remote research root configured in `config/remote.local.psd1`.

## Layout

```text
scripts/remote/
  README.md
  doctor.ps1
  ensure-connectivity.ps1
  deploy-remote-bin.ps1
  sync-code.ps1
  submit-autoresearch-trial.ps1
  submit-smoke-test.ps1
  submit-job.ps1
  check-job.ps1
  fetch-results.ps1
  cancel-own-job.ps1
  lib/
    common.ps1
    ssh.ps1
    paths.ps1
    result.ps1
  bootstrap/
    verify-local-tunnel-prereqs.ps1
    verify-remote-proxy-prereqs.ps1
  remote-bin/
    researchops_common.sh
    run_autoresearch_trial.sh
    run_smoke_test.sh
    run_train.sh
    check_job.sh
    cancel_job.sh

config/
  autoresearch.example.psd1
  autoresearch-train.example.psd1
  remote.example.psd1
```

## First checks

Run the read-only health check:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/remote/doctor.ps1 -Json
```

Make sure the proxy tunnel is alive, then verify SSH and remote proxy status:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/remote/ensure-connectivity.ps1 -Json
```

## Safety model

The scripts intentionally do not let an agent freely compose SSH commands.
Experiment automation should call these fixed entrypoints only.

- Daily paper automation may call `doctor.ps1` only.
- Auto experiment loops may call `ensure-connectivity.ps1`, `sync-code.ps1`,
  `submit-autoresearch-trial.ps1`, `check-job.ps1`, and `fetch-results.ps1`.
- `submit-smoke-test.ps1` remains available for manual fixed smoke checks.
- Full training requires `submit-job.ps1 -ConfirmFullTraining`.
- Remote operations use the normal SSH host alias, never the tunnel-only alias.
- The tunnel alias is reserved for maintaining the local proxy port.
- Remote experiment files are created under `<remote-workspace-root>/experiments/<experiment-id>`.
- Fixed remote entry scripts live under `<remote-workspace-root>/bin`.

The local copies of those remote entry scripts are kept in
`scripts/remote/remote-bin/` and deployed to `<remote-workspace-root>/bin`.

## Local configuration

Copy `config/remote.example.psd1` to `config/remote.local.psd1` for real
server values. Copy `config/autoresearch-train.example.psd1` to
`config/autoresearch-train.local.psd1` for real training paths. The local files
are ignored by Git.

## Local Codex Autoresearch Adapter

The project-local `codex-autoresearch` skill is installed under
`.agents/skills/codex-autoresearch/`, with the upstream Windows skill preserved
under `.agents/vendor/codex-autoresearch-windows-skill/`.

This adapter is foreground-only and explicit-invocation-only. It must not use
background runtime control, `codex exec`, hooks, Full Access bypass paths, or
arbitrary SSH during skill launch.

The Karpathy-style GPU path is a bounded remote trial bridge, not a free-form
SSH surface. After explicit pre-launch approval, `$codex-autoresearch` may use:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\remote\submit-autoresearch-trial.ps1 -ExperimentId <id> -Json
```

Trial parameters live in `config/autoresearch-train.example.psd1`; copy that to
`config/autoresearch-train.local.psd1` for machine-specific values. Full
training still requires a separate explicit
`scripts\remote\submit-job.ps1 -ConfirmFullTraining` command.

Check the local adapter state with:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\autoresearch\doctor.ps1 -Json
```

The current workspace root must be a git repository before a managed
autoresearch run can start, because the helper scripts store a git-local pointer
to `autoresearch-results/context.json`.
