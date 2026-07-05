# Project Guide

This project-local adapter enables only the foreground `$codex-autoresearch`
workflow in the current Codex App session.

## Launch

```text
$codex-autoresearch
Improve the measurable target in this repository.
```

Codex should:

1. scan the repo,
2. propose a metric, scope, verification command, and guard,
3. ask for your approval,
4. initialize `autoresearch-results/results.tsv`, `state.json`, and
   `context.json`,
5. iterate in the same foreground Codex session.

The default workspace root comes from the launch context. If Codex starts inside
a Git repo, use that repo root; otherwise use the current launch directory. It
should not silently widen the workspace root to a parent directory.

## Disabled

- Background runtime control.
- `Mode: exec` and `codex exec`.
- Hooks installation or repair.
- Full Access and sandbox bypass flags.
- Arbitrary SSH or full GPU training during the skill launch.

## Karpathy-Style Remote Trial

After explicit pre-launch approval, the foreground loop may use the fixed remote
trial bridge as its verification command:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\remote\submit-autoresearch-trial.ps1 -ExperimentId <id> -Json
```

Trial parameters live in `config\autoresearch-train.example.psd1`; copy it to
`config\autoresearch-train.local.psd1` for local overrides. Full training still
stays outside `$codex-autoresearch` and requires
`scripts\remote\submit-job.ps1 -ConfirmFullTraining`.

The original upstream guide is preserved in
`.agents/vendor/codex-autoresearch-windows-skill/docs/GUIDE.md`.
