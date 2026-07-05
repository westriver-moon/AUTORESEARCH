# Autoresearch Adapter Contract

This directory contains project-local checks for the adapted
`codex-autoresearch` skill.

The supported mode for this project is intentionally narrow:

- explicit invocation only with `$codex-autoresearch`
- foreground mode only in the current Codex App session
- helper scripts called with `python`
- no background runtime controller
- no `codex exec`
- no hook install or repair
- no Full Access or sandbox bypass path
- no arbitrary SSH or full GPU training during skill launch
- optional Karpathy-style GPU verification only through
  `scripts\remote\submit-autoresearch-trial.ps1`

Run the read-only doctor:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\autoresearch\doctor.ps1 -Json
```

The doctor does not initialize git, install hooks, launch Codex, connect to SSH,
or start training. It reports `ok: false` when the project is not ready for a
managed autoresearch run, for example when the target project is not a git
repository.

For Karpathy-style runs, use the remote trial bridge as the verify command:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\remote\submit-autoresearch-trial.ps1 -ExperimentId <id> -Json
```

Trial training parameters are documented in
`config\autoresearch-train.example.psd1`.

Local overrides may be placed in `config\autoresearch.local.psd1`. Keep that
file uncommitted.
