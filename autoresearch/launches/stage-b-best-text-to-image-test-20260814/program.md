---
goal: "Evaluate the retained best Stage-B text encoder as a pure text-to-original-RGB-image ReID model on the SYSU-MM01 test split."
metric: "Rank-1"
direction: "higher"
budget_mode: "fixed"
worker_count: 1
keep_threshold: 0.0
stop_conditions:
  - "stop after the single fixed-checkpoint evaluation completes"
mutable_paths:
  - "scripts/evaluation/run_stage_b_best_text_to_image.py"
notes:
  - "Use the retained SALT_R_TEXT_VISUAL epoch-23 checkpoint, whose historical Fusion Rank-1 is 84.0783%."
  - "Use only the legacy identity-conditioned Blip RGB caption as the query representation; do not use IR image features."
  - "Search the original SYSU-MM01 RGB test gallery with derived SR modalities disabled."
  - "Use all-search single-shot evaluation averaged over the canonical 10 gallery trials, seed 0."
  - "Lease only physical GPU 1 or 3; never use physical GPU 0 or the GPU 2 training job."
---

This is a fixed-checkpoint protocol evaluation, not training or model selection.
