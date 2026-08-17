## Autoresearch v2 control inputs

This directory contains project-owned programs and schema v2 targets. The
runtime is generic: each target supplies a repository, argv, environment,
result-file contract, artifacts, declared inputs, and optional resource lease.

- `program-example.md` is a generic program template.
- `targets/example-cpu.yaml` is a schema example; replace `repo.path` before use.
- Other programs and targets may be project-specific, but the runtime must not
  interpret their domain semantics.
