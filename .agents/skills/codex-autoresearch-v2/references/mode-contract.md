# Mode Contract

Autoresearch v2 has two agent-facing modes:

- Invocation mode: use `$codex-autoresearch-v2`; call the completed runtime and
  edit only run inputs or target overlays.
- Development mode: use `$codex-autoresearch-v2-dev`; edit the skill, runtime,
  guard, tests, or packaged plugin.

The authoritative policy lives in `.codex/research-policy.json`.

Invocation mode must not modify sealed implementation paths:

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

Use the guard before committing or when a task may have touched implementation
files:

```powershell
scripts/remote/guard-autoresearch-mode.ps1 -Mode invoke -FromGit -Json
```

Development mode may modify sealed paths, but should still run the guard in
`develop` mode to make the intent explicit:

```powershell
scripts/remote/guard-autoresearch-mode.ps1 -Mode develop -FromGit -Json
```
