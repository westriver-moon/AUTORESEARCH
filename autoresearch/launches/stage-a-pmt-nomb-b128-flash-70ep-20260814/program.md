---
goal: "Measure the effect of extending the repaired Flash Attention PMT-ViT Stage-A no-MBPatch effective-batch-128 run from 24 to 70 epochs."
metric: "Rank-1"
direction: "higher"
budget_mode: "fixed"
worker_count: 1
keep_threshold: 0.0
stop_conditions:
  - "stop after the single 70-epoch Stage-A run completes"
mutable_paths:
  - "configs/stage_a/reproduction/source_core/stage_a_current_best_no_mbpatch_pasd_rgb_ir_geomatched_512x256_1view_b64_flash.yaml"
  - "scripts/reproduction/run_stage_a_pmt_no_mbpatch_b64_flash.py"
notes:
  - "Keep the repaired Flash Attention evaluation implementation from commit c2a07409175b00da90480660a616b7b5246fdaef."
  - "Preserve Stage-A, PMT-ViT, no MBPatch, seed 0, SYSU all-search single-shot 10-gallery-trial evaluation, batch_size 64, num_pos 4, and effective RGB-plus-IR batch 128."
  - "Change only the planned training length to 70 epochs, plus result-file extraction needed by Autoresearch v2."
  - "Lease one physical RTX 3090 from GPUs 1, 2, and 3 only; never use physical GPU 0."
---

Run one controlled 70-epoch comparison and retain its aggregate SYSU-MM01 metrics and checkpoints.
