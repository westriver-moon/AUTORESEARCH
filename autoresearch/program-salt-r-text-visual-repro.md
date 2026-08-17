---
goal: Reproduce the recorded SALT_R_TEXT_VISUAL SYSU-MM01 result from the pinned baseline implementation.
metric: Rank-1
direction: higher
budget_mode: fixed
worker_count: 1
keep_threshold: 0.0
stop_conditions:
  - stop after the single baseline reproduction completes
mutable_paths:
  - configs/reproduction/salt_r_text_visual_84_gpu.yaml
  - scripts/reproduction/run_salt_r_text_visual_repro.py
notes:
  - Use one leased GPU selected only from physical GPUs 1, 2, and 3.
  - Preserve the canonical checkpoint and historical metric log as read-only evidence.
---

# SALT_R_TEXT_VISUAL 84.0783 reproduction

Run one isolated 30-epoch SYSU-MM01 all-search, single-shot, 10-trial
reproduction from the recorded Stage-B warm start. Select the best evaluation
epoch by Rank-1 and retain the paired mAP and mINP from that same epoch.

