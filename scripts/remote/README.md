# Remote Script Contract

This directory is the only supported interface between research automation and
the remote GPU host.

The remote workspace root is `/home/cgv841/ybj`. Automation is allowed to
create and manage files under this root through the fixed entrypoints below.
The deployed remote shell scripts live in `/home/cgv841/ybj/bin`, and their
local source copies are kept in `scripts/remote/remote-bin`.

## Entry points

```text
doctor.ps1               Read-only health check.
ensure-connectivity.ps1  Starts the local tunnel helper when needed, then checks SSH and proxy status.
deploy-remote-bin.ps1    Deploys fixed remote shell entrypoints to /home/cgv841/ybj/bin.
sync-code.ps1            Copies a local project path into the remote experiment workspace.
submit-autoresearch-trial.ps1
                         Runs a bounded Karpathy-style trial verify command.
submit-smoke-test.ps1    Runs the fixed remote smoke-test entrypoint.
submit-job.ps1           Runs the fixed remote full-training entrypoint only with explicit confirmation.
check-job.ps1            Runs the fixed remote status entrypoint.
fetch-results.ps1        Fetches approved result files from the remote experiment directory.
cancel-own-job.ps1       Cancels only the job associated with the given experiment id.
```

## Required parameters

All experiment-scoped scripts accept:

```powershell
-ExperimentId <id>
-Json
-RemoteHost <ssh-alias>
-SshConfigPath <path>
```

`ExperimentId` must match:

```text
^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$
```

## Output

Each script writes a JSON status document to:

```text
experiments/<experiment-id>/remote/
```

`doctor.ps1` writes no experiment file unless `-ExperimentId` is supplied.

Remote experiment files are expected under:

```text
/home/cgv841/ybj/experiments/<experiment-id>/
```

## Prohibited behavior

- Do not call arbitrary SSH commands from research automation.
- Do not use `lab-server-codex-tunnel` for experiment work.
- Do not read SSH private key contents.
- Destructive deletion needs a dedicated confirmed entrypoint.
- Do not run full training without `submit-job.ps1 -ConfirmFullTraining`.

## Autoresearch Trial

`submit-autoresearch-trial.ps1` is the only remote GPU entrypoint intended for
the `$codex-autoresearch` loop. It runs `run_autoresearch_trial.sh` with a
bounded timeout and smoke-batch limit, then writes status under
`experiments/<experiment-id>/remote/`.

Deploy local remote entrypoints before using a newly added or changed script:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\remote\deploy-remote-bin.ps1 -Json
```

Training parameters can be supplied through
`config/autoresearch-train.local.psd1` or command-line overrides such as
`-Gpu`, `-MaxSeconds`, `-SmokeBatches`, and `-RemoteConfigPath`.
