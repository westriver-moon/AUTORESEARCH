---
goal: Measure whether the historical SALT 84 Stage-B objective transfers to IR-query versus RGB-plus-caption retrieval when only the ID-loss Fusion image source is changed from IR to RGB.
metric: Rank-1
direction: higher
budget_mode: fixed
worker_count: 1
keep_threshold: 0.0
stop_conditions:
  - stop after the single 30-epoch training run completes
mutable_paths:
  - src/salt_vi/engine/build.py
  - src/salt_vi/retrieval/registry.py
  - src/salt_vi/retrieval/ir_to_rgb_text_legacy_triangle.py
  - src/salt_vi/tests/test_ir_to_rgb_text_plugin.py
  - configs/experiments/ir_to_rgb_text_fusion84_30/train.yaml
  - scripts/training/run_ir_to_rgb_text_fusion84_30.py
notes:
  - Initialize from the verified best frozen-visual Stage-A epoch-24 checkpoint.
  - Preserve the historical ID-loss composition and the RGB-IR, RGB-Text, and IR-Text hard-triplet triangle.
  - Replace only Fusion(IR, Text) with Fusion(RGB, Text) at pa=0.5.
  - Use standard two-modality SwinIR array inputs and evaluate IR queries against RGB-plus-image-caption galleries.
  - Use physical GPU 3 only; never use GPU 0.
---

# SALT IR-to-RGB+Text with the historical 84 loss

Train for 30 epochs from the verified Stage-A checkpoint with the visual
backbone frozen. Evaluate SYSU-MM01 all-search, single-shot, 10-trial Rank-1,
mAP, and mINP before training and after every epoch.
