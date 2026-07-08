## Autoresearch v2

This directory contains the project-local control plane for remote-first
autoresearch.

- `program.md` is the human-maintained research program.
- `targets/` contains machine-readable target specs.
- `../config/autoresearch-v2.example.psd1` contains local control defaults.
- The default Stage A target assumes the server git root is `/home/cgv841/ybj`
  and the training code lives under the `TVI-LFM/` subdirectory.

The v2 runtime keeps run artifacts under `../autoresearch-runs/<run-tag>/`.

Typical flow:

1. Update `program.md`.
2. Tune or duplicate a target in `targets/`.
3. Deploy the remote controller.
4. Bootstrap a run tag.
5. Inspect mutable files, edit locally, apply to a worker, then baseline/run.
6. Poll status, collect artifacts, and repeat.
