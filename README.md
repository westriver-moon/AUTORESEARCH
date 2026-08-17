# Codex Autoresearch v2

This repository contains a project-local, remote-first autoresearch system. Its
generic controller is `scripts/remote/autoresearch-v2.ps1`; every experiment
supplies an explicit program and schema-v2 target instead of relying on a
project-specific training adapter.

## Architecture

```text
.agents/skills/codex-autoresearch-v2/      invocation instructions
.agents/skills/codex-autoresearch-v2-dev/  development boundary
scripts/remote/                            canonical local/remote runtime
config/autoresearch-v2.example.psd1        public defaults
config/autoresearch-v2.local.psd1          ignored host profiles
autoresearch/                              program and target inputs
autoresearch-runs/                         ignored run outputs
plugins/codex-autoresearch-v2/              generated plugin snapshot
tests/autoresearch_v2/                     regression tests
```

SSH credentials and jump routing remain in the user's OpenSSH configuration.
Target repositories, commands, metrics, artifacts, and optional resource
leases are declared by the target rather than the runtime.

## Start

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\remote\select-profile.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\remote\autoresearch-v2.ps1 -Mode access-doctor -RemoteProfile <profile> -Json
```

See `scripts/remote/README.md` for the controller interface and boundaries.
Generate the versioned plugin with `scripts/package-autoresearch-v2-plugin.ps1`.
The authoritative invoke/develop policy is `.codex/research-policy.json`.
