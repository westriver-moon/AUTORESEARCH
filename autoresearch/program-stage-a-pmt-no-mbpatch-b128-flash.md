---
goal: Measure the Stage-A batch-size effect for the no-MBPatch PMT-ViT recipe using Flash Attention and an effective cross-modal batch of 128 images.
metric: Rank-1
direction: higher
budget_mode: fixed
worker_count: 1
keep_threshold: 0.0
stop_conditions:
  - stop after the single 24-epoch Stage-A run completes
mutable_paths:
  - configs/stage_a/reproduction/source_core/stage_a_current_best_no_mbpatch_pasd_rgb_ir_geomatched_512x256_1view_b64_flash.yaml
  - scripts/reproduction/run_stage_a_pmt_no_mbpatch_b64_flash.py
notes:
  - Preserve the current no-MBPatch PMT-ViT Stage-A recipe, seed, data, losses, optimizer, schedule, and evaluation protocol.
  - Use config batch_size 64 and num_pos 4, yielding P=16 and 128 total visible-plus-IR images per step.
  - Require the Flash Attention backend and PMT gradient checkpointing.
  - Lease one physical RTX 3090 from GPUs 1, 2, and 3 only; never use GPU 0.
---

# PMT-ViT Stage-A no-MBPatch effective-batch-128 comparison

Train one 24-epoch SYSU-MM01 Stage-A run with geometry-matched one-view PASD
RGB and IR inputs at 512x256. Evaluate using the existing all-search,
single-shot, 10-gallery-trial protocol and select the best epoch by Rank-1,
retaining mAP and mINP from that same epoch.
