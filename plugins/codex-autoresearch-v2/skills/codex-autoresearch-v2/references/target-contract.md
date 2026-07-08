# Target Contract

Each target YAML must define:

- `name`
- `repo.remote_root`
- `repo.base_ref`
- `repo.mutable_paths`
- `run.command`
- `run.metric.parser`
- `run.metric.direction`

Optional sections:

- `repo.readonly_paths`
- `run.budget_minutes`
- `artifacts.collect`
- `training`
- `gpu`
