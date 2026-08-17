---
goal: Determine whether the original SALT R_TEXT_VISUAL objective can exceed its recorded SYSU-MM01 result through conservative low-learning-rate continuation to 100 cumulative epochs.
metric: Rank-1
direction: higher
budget_mode: fixed
worker_count: 1
keep_threshold: 0.0
stop_conditions:
  - stop after the single 76-epoch continuation completes
mutable_paths:
  - configs/experiments/r_text_visual_extended_lr_100/continuation.yaml
  - scripts/training/run_r_text_visual_extended_lr_100.py
notes:
  - Continue from the retained original-config epoch-23 checkpoint, which represents 24 completed epochs.
  - Run 76 additional epochs for exactly 100 cumulative epochs.
  - Preserve the original loss, modality-pair weights, fusion, frozen visual backbone, dataset, and raw evaluation protocol.
  - Change only the continuation learning rates, fresh optimizer state, warmup length, and extended cosine schedule.
  - Use one leased GPU selected only from physical GPUs 2 and 3.
---

# SALT R_TEXT_VISUAL low-LR continuation to 100 epochs

Continue the retained epoch-23 checkpoint with a fresh AdamW optimizer and a
conservative cosine learning-rate sweep. Evaluate SYSU-MM01 all-search,
single-shot, 10-trial metrics every epoch without TTA, MER, or re-ranking.
