---
name: codex-autoresearch
description: "Project-local foreground-only autoresearch loop for Codex App. Use only when the user explicitly invokes $codex-autoresearch for a measurable improve-verify loop. Background, exec, hooks, and Full Access are disabled in this project."
metadata:
  short-description: "Foreground-only improve-verify loop"
---

# codex-autoresearch

Autonomous goal-directed iteration. Modify -> Verify -> Keep/Discard -> Repeat.

## Project-Local Windows App Policy

This copy is installed for the current project only at
`.agents/skills/codex-autoresearch/`. These policy overrides take precedence
over any upstream background, exec, hook, or Full Access guidance in this skill
bundle:

- Invoke only when the user explicitly writes `$codex-autoresearch`.
- Use foreground mode only. Keep all iteration in the current Codex App session.
- Do not launch, start, resume, stop, or status-check background runtimes.
- Do not use `exec` mode or `codex exec`.
- Do not install, repair, or enable hooks. Never run
  `autoresearch_hooks_ctl.py install`.
- Do not use `--dangerously-bypass-approvals-and-sandbox`, Full Access, or any
  bypass path.
- On Windows, call helper scripts with `python`, not `python3`.
- Do not connect SSH or start GPU training unless the user gives a separate,
  explicit instruction outside this skill launch.
- Karpathy-style remote GPU trials are the only exception: after explicit
  pre-launch approval, foreground runs may use the fixed verify bridge
  `scripts\remote\submit-autoresearch-trial.ps1` plus `check-job.ps1` and
  `fetch-results.ps1`. Do not compose arbitrary SSH commands. Do not use
  `submit-job.ps1 -ConfirmFullTraining` from inside `$codex-autoresearch`;
  full training remains a separate human-confirmed action.

## When Activated

1. Classify the request as `loop`, `plan`, `debug`, `fix`, `security`, or `ship`, and parse any inline config from the prompt. If the prompt asks for `exec`, background, hooks, or Full Access, explain that those paths are disabled for this project.
2. Load `references/core-principles.md` and `references/structured-output-spec.md`. For active execution modes (`loop`, `debug`, `fix`, `security`, `ship`), also load `references/runtime-hard-invariants.md`.
3. Load only the additional references the current situation needs:
   - `references/session-resume-protocol.md` when resuming or controlling an existing run
   - `references/environment-awareness.md` before choosing hardware-sensitive work
   - `references/interaction-wizard.md` for every new interactive launch (`loop`, `debug`, `fix`, `security`, `ship`) before execution begins
   - `references/results-logging.md` only when debugging TSV/state semantics or helper behavior directly
4. Load the selected mode workflow reference plus only the detailed cross-cutting protocols that actually apply (`lessons`, `pivot`, `health-check`, `parallel`, `web-search`, `hypothesis-perspectives`).
5. Use the bundled helper scripts when stateful artifacts are involved. Resolve them relative to the loaded skill bundle root (`<skill-root>/scripts/...`), not the target repo root. In this repo-local Windows install this means commands such as `python .agents/skills/codex-autoresearch/scripts/autoresearch_init_run.py --repo <primary_repo> --workspace-root <workspace_root> ...`. Use foreground helpers such as `autoresearch_init_run.py`, `autoresearch_record_iteration.py`, `autoresearch_select_parallel_batch.py`, `autoresearch_supervisor_status.py`, and read-only health/resume helpers. For Karpathy-style GPU verification, use only the project remote bridge scripts under `scripts\remote\`. Do not call `autoresearch_runtime_ctl.py` or `autoresearch_hooks_ctl.py`.
6. Execute the selected workflow exactly as written and produce the required structured output and artifacts.

### Disabled Exec Contract

`exec` mode is disabled in this project. Do not create exec scratch state,
invoke `codex exec`, emit exec JSON-only output, or use upstream exec helper
flows during normal operation. Existing upstream exec helper files may remain in
the bundle only so the original code copy is intact and Python unit tests can
cover helper behavior.

## Core Loop

1. Read the relevant context.
2. Define a mechanical success metric.
3. Establish a baseline.
4. Make one focused change.
5. Verify with a command.
6. Keep or discard the change.
7. Log the result.
8. Repeat.

## Modes

| Mode | Purpose | Primary Reference |
|------|---------|-------------------|
| `loop` | Run the autonomous improvement loop | `references/loop-workflow.md` |
| `plan` | Convert a vague goal into a launch-ready config | `references/plan-workflow.md` |
| `debug` | Hunt bugs with evidence and hypotheses | `references/debug-workflow.md` |
| `fix` | Iteratively reduce errors to zero | `references/fix-workflow.md` |
| `security` | Run a structured security audit | `references/security-workflow.md` |
| `ship` | Gate and execute a ship workflow | `references/ship-workflow.md` |

Use `Mode: <name>` in the prompt to force a specific subworkflow.
If `Mode: exec` is requested, decline that mode and offer foreground `loop`,
`debug`, or `fix` instead.

## Required Config

For the generic loop, the following fields are needed internally. Codex infers them from the user's natural language input and repo context, then fills gaps through guided conversation:

- `Goal`
- `Scope`
- `Metric`
- `Direction`
- `Verify`

Optional but recommended:

- `Guard`
- `Iterations`
- `Run tag`
- `Stop condition`

For every new interactive run, use the wizard contract in `references/interaction-wizard.md`.

## Explicit Run Modes

- `$codex-autoresearch` is the only primary human-facing entrypoint.
- For a new interactive run, scan the repo, ask the confirmation questions, and use **foreground** mode. Do not ask the user to choose background in this project.
- If the user chooses **foreground**, keep the loop in the current Codex session. Use the shared helper scripts (`autoresearch_init_run.py --repo <primary_repo> --workspace-root <workspace_root>`, `autoresearch_record_iteration.py`, `autoresearch_select_parallel_batch.py`, `autoresearch_supervisor_status.py --repo <primary_repo>`) and do not create launch/runtime control artifacts.
- If the user asks for **background**, say that background mode is not enabled for this project and offer foreground mode.
- If the user resumes an existing foreground run, inspect `autoresearch-results/state.json` and continue in foreground mode only. `autoresearch_set_session_mode.py` remains an internal/scripted recovery helper, not a normal user-facing step.
- Treat the repo where the run starts as the **primary repo**. Single-repo runs are the default. If the task truly spans multiple codebases, declare **companion repos** explicitly and give each repo its own scope instead of stuffing absolute paths into one mixed scope string.
- For a new interactive run, default the `workspace_root` from the launch context: if Codex started inside a git repo, use that repo root; otherwise use the current launch directory. Do not silently widen to a parent workspace just because sibling repos or old artifacts exist. Only widen when the user explicitly confirms a broader multi-repo workspace, and show the resulting `Results directory` in the confirmation summary.
- Never create `autoresearch-results/launch.json`, `autoresearch-results/runtime.json`, or `autoresearch-results/runtime.log` for this project-local foreground mode.
- Do not check, install, repair, or enable managed hooks for new runs. Hooks are intentionally disabled in this project.
- For `status` or `stop` requests, explain that background runtime control is disabled. For `resume`, resume only foreground artifacts in the current session.
- `exec` mode is disabled. Do not use it as an advanced or CI path in this project.

## Hard Rules

1. **Ask before act for new foreground launches.** For `loop`, `debug`, `fix`, `security`, and `ship`, ALWAYS scan the repo and ask at least one round of clarifying questions before the run starts. Load and follow `references/interaction-wizard.md` for every new interactive launch, but skip background and hook setup questions.
2. **Respect foreground-only execution after launch approval.** In interactive modes, once the user says "go" (or equivalent: "start", "launch", or any clear approval), stay in the current session and do not call `autoresearch_runtime_ctl.py launch`, `codex exec`, or any hook installer.
3. **Never ask after the user approves the run.** Once the user has approved `go` in foreground mode, do not pause mid-run to ask anything -- not for clarification, not for confirmation, not for permission. If you encounter ambiguity during the loop, apply best practices and keep going. The user may be asleep.
4. Read all in-scope files before the first write.
5. One focused change per iteration.
6. Mechanical verification only.
7. Commit before verification only when every managed repo's worktree stays within that repo's declared scope or autoresearch-owned artifacts. Foreground runs must honor this before creating a trial commit.
8. Never stage or revert unrelated user changes.
9. Keep run artifacts uncommitted and never stage them.
10. Use the rollback strategy approved during setup. In a dedicated experiment branch/worktree with pre-launch approval, `git reset --hard HEAD~1` is allowed; otherwise use `git revert --no-edit HEAD`.
11. Discard gains under 1% that add disproportionate complexity.
12. Unlimited runs by default unless the user explicitly asks for `Iterations: N`.
13. External ship actions (deploy, publish, release) must be confirmed during the pre-launch wizard phase. If not confirmed before launch, skip them and log as blocker.
14. Do not ask "should I continue?". Once launched, keep the chosen run mode active until interrupted or a hard blocker / configured terminal condition appears (see `references/autonomous-loop-protocol.md` Stop Conditions for the full definition).
15. During active execution, keep `references/runtime-hard-invariants.md` as the primary runtime checklist. Foreground's core persistent artifacts are `autoresearch-results/results.tsv`, `autoresearch-results/state.json`, `autoresearch-results/context.json`, and `autoresearch-results/lessons.md`; do not create background runtime artifacts.
16. When stuck (3+ consecutive discards), use the PIVOT/REFINE escalation ladder from `references/pivot-protocol.md` instead of brute-force retrying.
17. Prefer the bundled helper scripts over hand-editing `autoresearch-results/results.tsv`, `autoresearch-results/state.json`, `autoresearch-results/context.json`, or runtime-control files. Always call them via the skill-bundle path (`<skill-root>/scripts/...`); never call bare `scripts/autoresearch_*.py` from the target repo root unless the skill bundle itself is actually installed there.
18. Do not use `exec` mode in this project. If asked for CI-style automation, offer a foreground plan or ask the user to explicitly approve a separate non-skill workflow.
19. After any context compaction event (the CLI warns about thread length and compaction), re-read `references/runtime-hard-invariants.md`, `references/core-principles.md`, and the selected mode workflow from disk before the next iteration. Do not rely on memory of those documents after compaction.
20. Every 10 iterations, perform the Protocol Fingerprint Check defined in `references/runtime-hard-invariants.md`. Use Phase 8.7 of `references/autonomous-loop-protocol.md` only for the detailed re-anchoring procedure. If any item fails, re-read all loaded runtime docs from disk before continuing.

## Structured Output

Every mode should follow `references/structured-output-spec.md`.

Minimum requirement:

- for interactive and user-facing modes, print a setup summary before the loop starts,
- for interactive and user-facing modes, print progress updates during the loop,
- for interactive and user-facing modes, print a completion summary at the end,
- write the mode-specific output files when the workflow defines an output directory.

## Quick Start

```text
$codex-autoresearch
I want to get rid of all the `any` types in my TypeScript code
```

```text
$codex-autoresearch
I want to make our API faster but I don't know where to start
```

```text
$codex-autoresearch
pytest is failing, 12 tests broken after the refactor
```

Codex scans the repo, asks targeted questions to clarify your intent, confirms
the foreground run, then starts the loop. You never need to write key-value
config.

## References

- `references/core-principles.md`
- `references/runtime-hard-invariants.md`
- `references/loop-workflow.md`
- `references/autonomous-loop-protocol.md`
- `references/interaction-wizard.md`
- `references/structured-output-spec.md`
- `references/modes.md`
- `references/plan-workflow.md`
- `references/debug-workflow.md`
- `references/fix-workflow.md`
- `references/security-workflow.md`
- `references/ship-workflow.md`
- `references/results-logging.md`
- `references/lessons-protocol.md`
- `references/pivot-protocol.md`
- `references/web-search-protocol.md`
- `references/environment-awareness.md`
- `references/parallel-experiments-protocol.md`
- `references/session-resume-protocol.md`
- `references/health-check-protocol.md`
- `references/hypothesis-perspectives.md`
