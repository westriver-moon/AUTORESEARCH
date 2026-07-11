# Codex Autoresearch Project Adapter

This is a project-local Windows Codex App adaptation of
`yourskenny/codex-autoresearch-windows-skill`.

The original repository is preserved under:

```text
.agents/vendor/codex-autoresearch-windows-skill/
```

This adapted skill copy lives under:

```text
.agents/skills/codex-autoresearch/
```

## Enabled

- Explicit invocation only: start with `$codex-autoresearch`.
- Foreground mode only: the loop stays in the current Codex App session.
- Project-local helper scripts called with `python`.
- Local artifacts under `autoresearch-results/`:
  - `results.tsv`
  - `state.json`
  - `context.json`
  - `lessons.md` when lesson extraction is used

## Disabled

- Implicit invocation.
- Background runtime control.
- `codex exec` / `Mode: exec`.
- Hooks install, repair, or enablement.
- `--dangerously-bypass-approvals-and-sandbox`.
- Full Access / sandbox bypass paths.
- SSH connections or GPU training during this skill launch unless separately
  requested outside the skill.

## Use

Open Codex in the target project and write:

```text
$codex-autoresearch
I want to improve the measurable target in this repo.
```

Codex should scan the repo, ask a concise confirmation question, show the metric
and verification command, then run in foreground only after you approve.

## Workspace Rule

Results directory stays in the launch context. The default workspace root comes
from the launch context: if Codex starts inside a Git repo, use that repo root;
otherwise use the current launch directory. Codex should not silently widen the
workspace root to a parent directory.

The confirmation summary should always show the chosen Results directory:

```text
Results directory: ./autoresearch-results/
```

## Verify This Adapter

From the project root:

```powershell
python -m unittest discover -s .agents\skills\codex-autoresearch\tests -q
python -m unittest discover -s tests -q
```

The project test suite includes a local simulated metric run that checks
`results.tsv`, `state.json`, retained improvements, regression rollback, and
that no Codex CLI background path is invoked.
