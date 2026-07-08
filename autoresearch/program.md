---
goal: Improve TVI-LFM Stage A retrieval quality through bounded autonomous
  code-search and experiment loops.
metric: primary_metric
direction: higher
budget_mode: medium
worker_count: 2
keep_threshold: 0.002
stop_conditions:
  - 12 consecutive discards
  - primary_metric >= 0.75
mutable_paths:
  - TVI-LFM/main.py
  - TVI-LFM/core/build.py
  - TVI-LFM/core/train.py
  - TVI-LFM/data_loader/loader.py
  - TVI-LFM/data_loader/sampler.py
  - TVI-LFM/tools/loss.py
  - TVI-LFM/network/model.py
  - TVI-LFM/network/pmt_vit.py
  - TVI-LFM/network/pmt_vit_adapter.py
  - TVI-LFM/network/gem_pool.py
  - TVI-LFM/config/stage_a/*.yaml
notes:
  - Prefer simple changes with measurable effects.
  - Keep failed hypotheses in lessons and move on.
  - Use remote workers continuously once launched.
---

# TVI-LFM Stage A Program

This program is intentionally short and operational.

The agent should:

- establish a baseline before chasing improvements,
- treat `/home/cgv841/ybj` as the remote git root and `TVI-LFM/` as the active subproject,
- keep the best retained commit on the remote best branch,
- use worker branches for speculative edits,
- discard regressions mechanically,
- refresh other workers to the best commit after an accepted improvement.
