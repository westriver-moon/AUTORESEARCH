# Project Examples

Use `$codex-autoresearch` explicitly and keep the run in foreground mode.

## Improve A Metric

```text
$codex-autoresearch
I want to reduce the failing test count in this repo.
```

Expected flow:

1. Codex scans the repo and proposes a failing-test metric.
2. Codex proposes a verify command such as `python -m unittest discover -s tests`.
3. You approve with `go`.
4. Codex initializes `autoresearch-results/results.tsv` and `state.json`.
5. Each iteration is kept only when the metric improves and the guard passes.

## Debug A Regression

```text
$codex-autoresearch Mode: debug
Find why the current smoke test regressed and fix it if the metric improves.
```

Expected flow:

1. Codex confirms the symptom and scope.
2. Codex chooses a mechanical reproduction command.
3. Codex runs foreground iterations until the regression is fixed, blocked, or
   the configured iteration cap is reached.

## Karpathy-Style GPU Trial

```text
$codex-autoresearch
Run a bounded TVI-LFM Stage A PMT_VIT trial loop. Use mAP as the metric, higher is better.
Verify with scripts\remote\submit-autoresearch-trial.ps1 and fetch/check the
trial result before deciding keep or discard.
```

Expected flow:

1. Codex confirms the editable scope, metric, and trial budget.
2. Codex uses `submit-autoresearch-trial.ps1` as the fixed verify command.
3. Codex reads the fetched metric and keeps only improving iterations.
4. Full training remains separate and is never launched by this skill.

## Disabled Requests

If the prompt asks for background, hooks, `Mode: exec`, `codex exec`, Full
Access, bypass flags, arbitrary SSH, or full training from inside the skill,
this adapter should decline that mode and offer a foreground run instead.

The original upstream examples are preserved in
`.agents/vendor/codex-autoresearch-windows-skill/docs/EXAMPLES.md`.
