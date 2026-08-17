---
goal: Repair Flash Attention evaluation and rerun the Stage-A no-MBPatch PMT-ViT effective-batch-128 comparison.
metric: Rank-1
direction: higher
budget_mode: fixed
worker_count: 1
keep_threshold: 0.0
stop_conditions:
  - stop after the single repaired 24-epoch Stage-A run completes
mutable_paths:
  - src/salt_vi/engine/test.py
  - src/salt_vi/tests/test_legacy_evaluator.py
  - configs/stage_a/reproduction/source_core/stage_a_current_best_no_mbpatch_pasd_rgb_ir_geomatched_512x256_1view_b64_flash.yaml
  - scripts/reproduction/run_stage_a_pmt_no_mbpatch_b64_flash.py
notes:
  - Enable CUDA autocast only for Flash Attention evaluation feature extraction; preserve legacy and SDPA evaluation behavior.
  - Preserve the current no-MBPatch PMT-ViT Stage-A recipe, seed, data, losses, optimizer, schedule, and 10-trial evaluation protocol.
  - Use config batch_size 64 and num_pos 4, yielding P=16 and 128 total visible-plus-IR images per step.
  - Lease one physical RTX 3090 from GPUs 1, 2, and 3 only; never use GPU 0.
---

# Repaired PMT-ViT Stage-A no-MBPatch batch-128 comparison

Validate the Flash evaluation regression, then train one 24-epoch SYSU-MM01
Stage-A run with geometry-matched one-view PASD RGB and IR inputs at 512x256.
Select the best epoch by aggregate 10-gallery-trial Rank-1 and retain mAP and
mINP from that same epoch.
