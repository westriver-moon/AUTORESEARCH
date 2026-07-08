---
name: codex-autoresearch-v2-dev
description: "Develop, repair, validate, or package the codex-autoresearch-v2 skill and remote-first runtime. Use when the user explicitly asks to change the autoresearch skill, runtime scripts, mode guard, tests, or versioned plugin package; this is the only autoresearch mode that may modify sealed implementation paths."
---

# codex-autoresearch-v2-dev

Use this skill in development mode for the autoresearch v2 implementation.

## Development Contract

- Keep `$codex-autoresearch-v2` as the invocation-only skill.
- Modify sealed implementation paths only when the user asks for development,
  repair, validation, packaging, or policy changes.
- Keep the invocation/runtime interface stable unless the user asks to change it.
- Update tests when changing mode boundaries, guard behavior, or package layout.
- Run the mode guard in `develop` mode before final validation when sealed paths
  were touched.

## Sealed Paths

Development mode may edit these paths; invocation mode may not:

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

## Guard

Use the project guard to prove mode intent:

```powershell
scripts/remote/guard-autoresearch-mode.ps1 -Mode develop -FromGit -Json
```

Use invocation mode guard tests to prove sealed paths are rejected:

```powershell
scripts/remote/guard-autoresearch-mode.ps1 -Mode invoke -ChangedFile .agents/skills/codex-autoresearch-v2/SKILL.md -Json
```

## Package

The versioned plugin package lives at:

```text
plugins/codex-autoresearch-v2
```

Keep its manifest version aligned with `.codex/research-policy.json` under
`autoresearch.packaged_plugin.version`.
