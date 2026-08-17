---
goal: Train the historical best R_TEXT_VISUAL Stage-B text configuration from the best PASD RN50 Stage-A checkpoint.
metric: Rank-1
direction: higher
budget_mode: fixed
worker_count: 1
keep_threshold: 0.0
stop_conditions:
  - stop after the single 30-epoch Stage-B run completes
mutable_paths:
  - configs/experiments/stage_b_rn50_pasd_r_text_visual_30/train.yaml
  - scripts/training/run_stage_b_rn50_pasd_r_text_visual_30.py
notes:
  - Initialize from the retained epoch-115 RN50 Stage-A checkpoint.
  - Preserve the historical best R_TEXT_VISUAL text/fusion/loss/optimizer recipe.
  - Adapt only architecture-specific fields and the geometry-matched PASD input source.
  - Use one leased physical GPU selected only from GPUs 1 and 3; never use GPU 0.
---

# RN50 PASD Stage-A to best R_TEXT_VISUAL Stage-B

Run one isolated SYSU-MM01 Stage-B training for 30 epochs. Evaluate the
all-search, single-shot, 10-gallery-trial protocol before training and after
every epoch. Select the checkpoint by highest Rank-1 and report mAP and mINP
from the same epoch.
