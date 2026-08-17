---
goal: "Measure where every test caption ranks its own identity in the original RGB gallery using the retained best Stage-B text encoder."
metric: "identity-balanced Rank-1"
direction: "higher"
budget_mode: "fixed"
worker_count: 1
keep_threshold: 0.0
stop_conditions:
  - "stop after the single fixed-checkpoint diagnostic completes"
mutable_paths:
  - "scripts/evaluation/run_stage_b_caption_identity_rank.py"
notes:
  - "Use all 6,587 Blip RGB captions belonging to the 96 SYSU-MM01 test identities."
  - "Rank gallery identities by the best-scoring original RGB image after sorting all gallery images."
  - "Report both caption-weighted and identity-balanced rank statistics over the canonical 10 single-shot gallery trials."
  - "Use the retained SALT_R_TEXT_VISUAL epoch-23 checkpoint and no IR query features."
  - "Lease only physical GPU 1 or 3."
---

This is a fixed-checkpoint diagnostic evaluation. It does not train or modify the checkpoint.
