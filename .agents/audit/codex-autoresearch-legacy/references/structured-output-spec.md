# Structured Output Specification

Every enabled `codex-autoresearch` mode must produce predictable output and,
where defined, predictable artifact files. This project-local adapter enables
foreground, human-readable modes only.

## Status Values

All modes share these status values (see `references/results-logging.md` for full schema):

| Status | Meaning |
|--------|---------|
| `baseline` | Initial measurement before any changes |
| `keep` | Change improved the metric and passed guard |
| `discard` | Change did not improve or failed guard |
| `crash` | Verification crashed or produced an error |
| `no-op` | No actual diff was produced |
| `blocked` | Hard blocker encountered, loop stopped |
| `refine` | Strategy adjustment within current approach |
| `pivot` | Strategy abandoned, fundamentally new approach |
| `search` | Web search performed for external knowledge |
| `drift` | Metric drifted from expected value during session resume |

## Common Response Sections

These sections apply to the enabled foreground/user-facing modes.

Before work starts:

1. `Setup`
2. `Config`
3. `Baseline`

During work:

1. `Iteration`
2. `Metric`
3. `Decision`

At completion:

1. `Summary`
2. `Artifacts`
3. `Next Actions`

## Common Iteration Line

Use this shape during loops:

```text
[iteration N] hypothesis -> metric result -> keep/discard/crash
```

Extended statuses for stuck recovery and search:

```text
[iteration N] [REFINE] adjusted strategy -> metric result -> refine
[iteration N] [PIVOT] abandoned strategy X, trying Y -> metric result -> pivot
[iteration N] [SEARCH] "query" -> found approach -> metric result -> search
```

Parallel batch notation:

```text
[iteration Na] [PARALLEL worker-a] hypothesis -> metric result -> keep (SELECTED)
[iteration Nb] [PARALLEL worker-b] hypothesis -> metric result -> discard
```

## Mode Output Templates

### loop

Required completion summary:

- goal
- baseline metric
- best metric
- keep/discard/crash/refine/pivot counts
- lessons extracted (count)
- environment summary (one line)
- artifact path

Artifact:

- `autoresearch-results/results.tsv`
- `autoresearch-results/lessons.md` (if lessons were extracted)
- `autoresearch-results/state.json` (session state snapshot, not committed to git; see `references/session-resume-protocol.md`)
- `autoresearch-results/context.json` (canonical workspace-owned run context for hooks, status, and resume)

### plan

Required reply sections:

- Goal
- Scope
- Metric
- Direction
- Verify
- Guard
- Launch Options

No output directory required unless the user asks to save artifacts.

### debug

Output directory:

```text
debug/{YYMMDD}-{HHMM}-{slug}/
  findings.md
  eliminated.md
  debug-results.tsv
  summary.md
```

`summary.md` must include:

- issue statement
- scope
- findings by severity
- disproven hypotheses count
- recommended next action

### fix

Output directory:

```text
fix/{YYMMDD}-{HHMM}-{slug}/
  fix-results.tsv
  blocked.md
  summary.md
```

`summary.md` must include:

- baseline error count
- final error count
- categories fixed
- blocked items
- guard status

### security

Output directory:

```text
security/{YYMMDD}-{HHMM}-{slug}/
  overview.md
  threat-model.md
  attack-surface-map.md
  findings.md
  coverage.md
  dependency-audit.md
  recommendations.md
  security-audit-results.tsv
```

### ship

Ship mode also persists the generic iterating-run artifacts:

- `autoresearch-results/results.tsv`
- `autoresearch-results/lessons.md` (if lessons were extracted)
- `autoresearch-results/state.json`
- `autoresearch-results/context.json`

Output directory:

```text
ship/{YYMMDD}-{HHMM}-{slug}/
  checklist.md
  ship-log.tsv
  summary.md
```

## Logging Rules

- TSV headers must be written exactly once.
- When helper-managed artifacts include timestamps (for example lessons entries or runtime/state metadata), they should use UTC.
- Workspace-owned artifact metadata should use the documented canonical paths. `context.json` and state config fields store absolute paths so hooks and control-plane helpers can resolve the active run without cwd guessing.
- Final summaries should reference every artifact created.
- Parallel workers use `[PARALLEL worker-{id}]` prefix.
- `exec` JSON-only output is disabled in this project-local adapter.
