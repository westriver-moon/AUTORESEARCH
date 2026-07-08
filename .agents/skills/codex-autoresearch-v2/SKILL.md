---
name: codex-autoresearch-v2
description: "Invoke the completed remote-first autoresearch v2 runtime with background workers, worker branches, and mechanical keep/discard decisions. Use only for calling the existing interface, preparing run inputs, checking status, collecting results, or launching/resuming/stopping runs; do not modify this skill, packaged plugin, or runtime code unless the user explicitly switches to codex-autoresearch-v2-dev."
---

# codex-autoresearch-v2

Use this skill in invocation mode. Treat the skill, runtime, guard, and packaged
plugin as sealed implementation code.

## Core Contract

- Human launch is explicit.
- After launch, the runtime may continue without mid-run confirmation.
- Remote SSH is allowed only to the approved research host from local config.
- Remote edits must stay inside the target's declared mutable paths.
- Keep/discard is mechanical and metric-driven.
- Worker branches are disposable; the best branch is the retained truth.
- Do not edit sealed autoresearch implementation paths in invocation mode.

## Mode Boundary

Invocation mode may edit run inputs and target overlays, then call the runtime.
It must not modify:

- `.agents/skills/codex-autoresearch-v2/**`
- `scripts/remote/guard-autoresearch-mode.ps1`
- `scripts/remote/autoresearch-v2.ps1`
- `scripts/remote/smoke-autoresearch-v2.ps1`
- `scripts/remote/lib/common.ps1`
- `scripts/remote/lib/ssh.ps1`
- `scripts/remote/lib/result.ps1`
- `scripts/remote/lib/paths.ps1`
- `scripts/remote/lib/autoresearch_v2.ps1`
- `scripts/remote/remote-bin/autoresearch_v2_*.py`
- `scripts/remote/remote-bin/run_autoresearch_v2_bridge.sh`
- `plugins/codex-autoresearch-v2/**`

Use `$codex-autoresearch-v2-dev` only when the user asks to develop, repair, or
package the skill/runtime itself. Check the boundary with:

```powershell
scripts/remote/guard-autoresearch-mode.ps1 -Mode invoke -FromGit -Json
```

## Inputs

- `autoresearch/program.md`
- `autoresearch/targets/*.yaml`
- `config/autoresearch-v2.local.psd1` or `config/autoresearch-v2.example.psd1`

## Main Runtime

Use the unified PowerShell entrypoint:

```text
scripts/remote/autoresearch-v2.ps1
```

The runtime supports:

- deploy
- doctor
- bootstrap
- inspect
- apply
- baseline
- run
- resume
- status
- collect
- stop
- sync-best

## References

- `references/mode-contract.md`
- `references/program-contract.md`
- `references/target-contract.md`
- `references/keep-discard-contract.md`
- `references/recovery-contract.md`
- `references/parallel-workers-contract.md`
