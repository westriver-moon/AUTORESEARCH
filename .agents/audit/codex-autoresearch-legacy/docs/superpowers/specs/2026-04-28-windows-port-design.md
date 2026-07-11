# Windows Port Design

## Goal

Make `codex-autoresearch` reliable on Windows while preserving the existing Linux CI behavior and skill protocol.

## Scope

The port focuses on helper scripts and tests. The skill text, mode semantics, result file schema, and artifact layout remain unchanged.

## Approach

Add a small cross-platform process utility layer for subprocess decoding, executable lookup, process identity, and termination. Use it from runtime, launch-gate, hook, workspace, and invariant helpers where platform differences currently leak through. Keep the existing workspace-owned `autoresearch-results/` layout and git-local pointer model.

## Behavior

- Subprocess output must not crash tests or helpers because of Windows code page differences.
- Runtime process inspection must work on Windows without `ps`.
- Runtime stop must terminate the recorded process on Windows and keep existing Unix process-group behavior where available.
- Command availability checks must understand Windows executable extensions through `PATHEXT`.
- Tests must include focused Windows regressions that fail against the previous behavior.

## Testing

Use targeted unit tests for the compatibility layer and runtime controller behavior, then run the full `unittest` suite where practical. The contributor gate remains Linux-oriented for shell smoke tests, but core Python behavior should be testable on Windows.
