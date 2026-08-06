# Input contract

## Program

The caller-selected Markdown file needs YAML front matter. Start from
`autoresearch/program-example.md`.

Required: `goal`, `metric`, `direction`, `budget_mode`, and `worker_count`.
Optional: `keep_threshold`, `stop_conditions`, `mutable_paths`, and `notes`.
`direction` is `higher` or `lower`.

## Target

Use integer `schema_version: 2`; missing or older versions fail with
`unsupported-schema`.

Required: `name`, `repo.path`, `repo.mutable_paths`, `run.argv`, and
`metric.direction`.

Optional: `repo.base_ref` (default `HEAD`), `repo.readonly_paths`, `run.cwd`
(default `.`), `run.env`, `run.budget_minutes`, `metric.path` (default
`metrics.json`), `metric.primary_key` (must be `primary_metric`), `artifacts`,
`provenance.inputs`, and `gpu.mode`/`selector`/`max_wait_seconds`.

`run.argv` is an argv array, not a shell command. Expansion is limited to
documented `AR2_*` values. Paths and globs must stay inside declared roots.
`gpu.mode` is `none` or `lease`.
