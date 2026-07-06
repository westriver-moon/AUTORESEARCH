# Remote Script Contract

This directory is the only supported interface between research automation and
the remote GPU host.

The remote workspace root is configured by `config/remote.local.psd1`.
Automation is allowed to create and manage files under that root through the
fixed entrypoints below. The deployed remote shell scripts live in
`<remote-workspace-root>/bin`, and their local source copies are kept in
`scripts/remote/remote-bin`.

## Entry points

```text
doctor.ps1               Read-only health check.
ensure-connectivity.ps1  Starts the local tunnel helper when needed, then checks SSH and proxy status.
deploy-remote-bin.ps1    Deploys fixed remote shell entrypoints to <remote-workspace-root>/bin.
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
<remote-workspace-root>/experiments/<experiment-id>/
```

## Prohibited behavior

- Do not call arbitrary SSH commands from research automation.
- Do not use the tunnel-only SSH alias for experiment work.
- Do not read SSH private key contents.
- Destructive deletion needs a dedicated confirmed entrypoint.
- Do not run full training without `submit-job.ps1 -ConfirmFullTraining`.

## Autoresearch Trial

`submit-autoresearch-trial.ps1` is the only remote GPU entrypoint intended for
the `$codex-autoresearch` loop. It runs `run_autoresearch_trial.sh` against the
TVI-LFM Stage A `PMT_VIT` training path with a bounded timeout, then writes
status under `experiments/<experiment-id>/remote/`.

The default training target is the TVI-LFM PMT recipe config:

```text
TVI-LFM/config/stage_a/pmt_vit_stage_a_pmt_recipe_288x144_768.yaml
```

`SmokeBatches` is retained as a compatibility field for the local automation
contract. TVI-LFM does not expose a batch-count smoke flag, so the effective
runtime boundary for trial and smoke entrypoints is `MaxSeconds`.

Deploy local remote entrypoints before using a newly added or changed script:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\remote\deploy-remote-bin.ps1 -Json
```

Training parameters can be supplied through
`config/autoresearch-train.local.psd1` or command-line overrides such as
`-Gpu`, `-MaxSeconds`, `-SmokeBatches`, and `-RemoteConfigPath`.

Set `Gpu = 'auto'` to let the fixed remote entrypoint choose an idle GPU with
`nvidia-smi` before launching. A GPU is considered idle when
`memory.used <= 1024 MiB` and `utilization.gpu <= 10%`; if no GPU matches, the
entrypoint fails instead of starting work on a busy card.

For TVI-LFM runs, the entrypoint writes a normalized ReID metric file to:

```text
<remote-workspace-root>/experiments/<experiment-id>/results/metrics.json
```

The JSON includes `primary_metric`, `mAP`, `rank1`, `mINP`, percent-scaled
copies, and the raw metric block. `primary_metric` uses `best_mAP` when present
and otherwise falls back to the last parsed `mAP`. The autoresearch loop should
use `primary_metric` or `mAP` with `Direction = 'higher'`.
