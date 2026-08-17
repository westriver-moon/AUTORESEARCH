---
goal: Improve the SALT R_TEXT_VISUAL SYSU-MM01 raw retrieval metrics with fusion-directed metric learning and conservative visual adaptation.
metric: Rank-1
direction: higher
budget_mode: fixed
worker_count: 1
keep_threshold: 0.0
stop_conditions:
  - stop after the two-stage 25 plus 75 epoch experiment completes
mutable_paths:
  - configs/experiments/fusion_directed_100/phase_a.yaml
  - configs/experiments/fusion_directed_100/phase_b.yaml
  - scripts/training/run_fusion_directed_100.py
notes:
  - Use one leased GPU selected only from physical GPUs 0, 2, and 3.
  - Keep SYSU-MM01 all-search single-shot 10-trial evaluation free of TTA, MER, and re-ranking.
  - Phase A trains fusion and text heads for 25 epochs with the visual backbone frozen.
  - Phase B starts from the Phase-A Rank-1 checkpoint and trains for 75 epochs while conservatively unfreezing only the last visual block.
---

# SALT fusion-directed 100-epoch experiment

Run one isolated two-stage experiment on the pinned SALT implementation. Direct
the cross-modal hard loss toward the deployed Fusion-query versus RGB-gallery
retrieval geometry, then permit low-rate adaptation of the final visual block.

