---
name: codex-autoresearch-v2-dev
description: "Develop, repair, validate, or package Autoresearch v2. Use for changes to its skills, remote runtime/access layer, guard, tests, policy, or plugin; only this mode may edit sealed implementation paths."
---

# codex-autoresearch-v2-dev

Use this skill in development mode.

## Rules

- Keep `$codex-autoresearch-v2` as the invocation-only skill.
- Treat `.codex/research-policy.json` as the sole authority for modes, sealed
  paths, mutable inputs, and plugin version; do not duplicate its lists.
- Keep the invocation/runtime interface stable unless the user asks to change it.
- Update tests when changing mode boundaries, guard behavior, or package layout.
- Edit canonical sources, never generated files under
  `plugins/codex-autoresearch-v2`.

## Verify and package

Before final validation, prove development intent:

```powershell
scripts/remote/guard-autoresearch-mode.ps1 -Mode develop -FromGit -Json
```

When changing boundaries, also prove invocation mode rejects a sealed path:

```powershell
scripts/remote/guard-autoresearch-mode.ps1 -Mode invoke -ChangedFile .agents/skills/codex-autoresearch-v2/SKILL.md -Json
```

Set the release version only at
`.codex/research-policy.json` at `autoresearch.packaged_plugin.version`, then
generate and validate the plugin:

```powershell
scripts/package-autoresearch-v2-plugin.ps1
```
