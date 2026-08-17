#!/usr/bin/env python3
"""Generate a deterministic BCC trace through the production sampler class."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import random
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


REPO = Path("/home/cgv841/worktrees/ybj-qwen-text-aug-grid-e30/TVI-LFM")
DATA_ROOT = Path("/home/cgv841/datasets/SYSU-MM01")
TEXT_ROOT = Path("/home/cgv841/ybj/TVI-LFM/datasets/sysu/Text/Blip_RGB")
INDEX = Path(
    "/home/cgv841/datasets/SYSU-MM01/Text/Blip_RGB_Qwen3_14B_AWQ/"
    "caption_qwen3_14b_awq_4x.json"
)
OUTPUT = Path(
    "/home/cgv841/ybj/AAAI27_SERVER_EXPORT_20260731/"
    "visual_evidence/caption_panels/bcc_sampling_trace"
)
SEED = 0
SELECTION_SEED = 20260731


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    os.chdir(REPO)
    sys.path.insert(0, str(REPO))
    from data_loader.dataset import SimpleTokenizer, tokenize
    from data_loader.qwen_caption_sampling import QwenCaptionPool

    originals_path = TEXT_ROOT / "train_text_Blip_RGB.npy"
    originals = np.load(originals_path)
    tokenizer = SimpleTokenizer()
    pool = QwenCaptionPool(
        index_path=INDEX,
        data_root=DATA_ROOT,
        original_captions=originals,
        tokenizer=tokenizer,
        tokenize_fn=tokenize,
        probability=0.5,
        strategy="balanced_cycle",
        seed=SEED,
    )
    payload = json.loads(INDEX.read_text(encoding="utf-8"))
    rng = random.Random(SELECTION_SEED)
    selected = sorted(rng.sample(range(len(pool.paths)), 5))
    rows = []
    for sample_index in selected:
        relative = pool.paths[sample_index]
        entry = None
        for key in (
            str(DATA_ROOT / relative),
            (DATA_ROOT / relative).as_posix(),
            relative,
            f"datasets/sysu/{relative}",
        ):
            if key in payload:
                entry = payload[key]
                break
        if entry is None:
            raise KeyError(relative)
        for epoch in range(8):
            pool.set_epoch(epoch)
            choice = pool.selection_index(sample_index)
            if choice is None:
                gate = "source"
                paraphrase_index = ""
                final_caption = str(originals[sample_index])
            else:
                gate = "paraphrase"
                paraphrase_index = int(choice)
                final_caption = str(entry["paraphrases"][int(choice)])
            rows.append(
                {
                    "anonymous_sample_id": f"BCC-{selected.index(sample_index)+1:02d}",
                    "sample_index": sample_index,
                    "image_id": Path(relative).name,
                    "epoch": epoch,
                    "gate": gate,
                    "paraphrase_index": paraphrase_index,
                    "final_caption": final_caption,
                }
            )
    OUTPUT.mkdir(parents=True, exist_ok=True)
    csv_path = OUTPUT / "bcc_sampling_trace.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    script_target = OUTPUT / "generate_bcc_sampling_trace.py"
    if not script_target.exists():
        try:
            os.link(Path(__file__).resolve(), script_target)
        except OSError:
            script_target.write_bytes(Path(__file__).read_bytes())
    sampler_path = REPO / "data_loader/qwen_caption_sampling.py"
    source_status = subprocess.check_output(
        ["git", "-C", str(REPO.parent), "status", "--short", "--", "TVI-LFM/data_loader/qwen_caption_sampling.py"],
        text=True,
    ).strip()
    manifest = {
        "status": "complete",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "production_sampler": "data_loader.qwen_caption_sampling.QwenCaptionPool",
        "sampler_sha256": sha256(sampler_path),
        "sampler_file_clean_against_commit": not bool(source_status),
        "source_commit": subprocess.check_output(
            ["git", "-C", str(REPO.parent), "rev-parse", "HEAD"], text=True
        ).strip(),
        "seed": SEED,
        "selection_seed": SELECTION_SEED,
        "probability": 0.5,
        "strategy": "balanced_cycle",
        "rgb_only": True,
        "epochs": list(range(8)),
        "sample_indices": selected,
        "row_count": len(rows),
        "csv_sha256": sha256(csv_path),
        "command": "python generate_bcc_sampling_trace.py",
        "note": "IR captions are not sampled because rgb_only=true.",
    }
    (OUTPUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
