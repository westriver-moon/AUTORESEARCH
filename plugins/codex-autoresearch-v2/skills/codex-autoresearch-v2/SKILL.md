---
name: codex-autoresearch-v2
description: "Run remote-first Autoresearch v2 through configured server profiles and schema-v2 targets. Use to diagnose access, bootstrap isolated workers, apply candidates, run or resume experiments, inspect status, and collect metrics or artifacts. Use codex-autoresearch-v2-dev for implementation or packaging changes."
---

# Codex autoresearch v2

Use this skill in invocation mode.
Call the generic runtime; keep project semantics in the program and target.

## Start

Before any SSH action, resolve a configured Profile from the active workspace
root. In non-interactive execution, never open the console picker. If the user
named a configured Profile, validate and select it explicitly:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\remote\select-profile.ps1 -RemoteProfile <profile> -NonInteractive
```

Otherwise resolve the configured `ActiveRemoteProfile` deterministically:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\remote\select-profile.ps1 -NonInteractive
```

Omit `-NonInteractive` only when a human explicitly asks to use the interactive
picker. Use the selector's JSON `remote_profile` for every controller call;
this selection overrides any earlier host or Profile. Then call:

```text
scripts/remote/autoresearch-v2.ps1
```

Commands: `access-doctor`, `access-ensure`, `deploy`, `doctor`, `bootstrap`,
`inspect`, `apply`, `baseline`, `run`, `resume`, `status`, `collect`, `stop`,
and `sync-best`.

## Workflow

1. Validate the program and explicit schema v2 target.
2. Run `access-doctor` when access needs verification, then `doctor`.
3. Bootstrap isolated worker branches/worktrees.
4. Establish one baseline.
5. Apply candidate changes only inside declared mutable paths.
6. Run or resume workers.
7. Inspect status and collect state, provenance, metrics, and artifacts.

## Hard rules

- Require explicit human launch.
- Restrict SSH to the configured research host.
- Require integer `schema_version: 2`; reject others with `unsupported-schema`.
- Execute `run.argv` unchanged; do not rewrite project configuration.
- Read metrics only from the result file, never stdout.
- For SYSU-MM01, distinguish run or split IDs from gallery trials; default to
  the 10-trial protocol and record only its aggregate metrics.
- For RegDB, state whether each result is from one numbered trial or a
  multi-trial mean.
- Do not write defensive code, stack patches, or add unnecessary safety gates.
- Do not use SHA-256 unless the user explicitly requests cautious deletion.
- Treat hard links, export copies, and alternate paths to one checkpoint as the
  same experiment; avoid hard links unless necessary.
- Do not edit sealed implementation paths in invocation mode.

Use `$codex-autoresearch-v2-dev` only when the user asks to develop, repair,
validate, or package the implementation. Check the boundary with:

```powershell
scripts/remote/guard-autoresearch-mode.ps1 -Mode invoke -FromGit -Json
```

## Load only when needed

- Program or target authoring: `references/input-contract.md`.
- Access, Profiles, SSH, tunnels, or proxies:
  `references/remote-access-contract.md`.
- Retention, recovery, or parallel workers: `references/runtime-contract.md`.
- Metrics, artifacts, or hashes: `references/result-provenance-contract.md`.
