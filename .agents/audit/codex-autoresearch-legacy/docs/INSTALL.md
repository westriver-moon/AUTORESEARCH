# Windows Installation

This repository is intended to be cloned and installed as a Codex Windows client
skill.

## Prerequisites

- Codex Windows client or Codex CLI.
- Git.
- Python 3.
- PowerShell.

## Install

```powershell
git clone https://github.com/yourskenny/codex-autoresearch-windows-skill.git
cd codex-autoresearch-windows-skill
powershell -ExecutionPolicy Bypass -File .\scripts\install_windows_skill.ps1
```

The skill is copied to:

```text
%USERPROFILE%\.codex\skills\codex-autoresearch
```

The installer also installs the managed autoresearch session hooks unless
`-NoHooks` is passed.

## Verify

Restart Codex, then run:

```powershell
codex debug prompt-input '$codex-autoresearch test'
```

Confirm that `codex-autoresearch` appears in the available skills list.

Check hooks:

```powershell
python "$env:USERPROFILE\.codex\skills\codex-autoresearch\scripts\autoresearch_hooks_ctl.py" status
```

Expected:

```json
{"ready_for_future_sessions": true}
```

## Update

```powershell
cd codex-autoresearch-windows-skill
git pull
powershell -ExecutionPolicy Bypass -File .\scripts\install_windows_skill.ps1
```

Restart Codex after updating.

## Install Without Hooks

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_windows_skill.ps1 -NoHooks
```

You can install hooks later:

```powershell
python "$env:USERPROFILE\.codex\skills\codex-autoresearch\scripts\autoresearch_hooks_ctl.py" install
```

## Manual Copy

```powershell
$dest = "$env:USERPROFILE\.codex\skills\codex-autoresearch"
Remove-Item -Recurse -Force $dest -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
Copy-Item -Recurse -Force . $dest
python "$dest\scripts\autoresearch_hooks_ctl.py" install
```

Restart Codex when done.

## Troubleshooting

If the skill does not appear:

1. Confirm `SKILL.md` exists at `%USERPROFILE%\.codex\skills\codex-autoresearch\SKILL.md`.
2. Restart Codex.
3. Run `codex debug prompt-input '$codex-autoresearch test'`.
4. Run the hook status command above.

If `codex` launches the wrong executable on Windows, use `codex.cmd` explicitly.
