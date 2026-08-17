#!/usr/bin/env python3
"""Create the SYSU RGB source-to-Qwen caption audit panel and source table."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import random
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
from PIL import Image
from torchvision import transforms


REPO = Path("/home/cgv841/worktrees/ybj-qwen-text-aug-grid-e30/TVI-LFM")
DATASET = Path("/home/cgv841/datasets/SYSU-MM01")
QWEN_ROOT = Path("/home/cgv841/datasets/SYSU-MM01/Text/Blip_RGB_Qwen3_14B_AWQ")
QWEN_JSON = QWEN_ROOT / "caption_qwen3_14b_awq_4x.json"
QWEN_MANIFEST = QWEN_ROOT / "manifest.shard-000-of-001.json"
CLIP_CHECKPOINT = Path("/home/cgv841/.cache/clip/ViT-B-16.pt")
OUTPUT = Path(
    "/home/cgv841/ybj/AAAI27_SERVER_EXPORT_20260731/"
    "visual_evidence/caption_panels/rgb_qwen_generation"
)
SEED = 20260731

VOCAB = {
    "color": {
        "black", "white", "gray", "grey", "red", "crimson", "blue", "green",
        "yellow", "brown", "pink", "purple", "violet", "orange", "maroon", "beige",
    },
    "upper": {"shirt", "tshirt", "jacket", "coat", "sweater", "hoodie", "blouse", "top", "dress"},
    "lower": {"pants", "trousers", "jeans", "shorts", "skirt", "dress"},
    "carry": {"bag", "backpack", "handbag", "purse", "phone", "mobile", "umbrella"},
    "gender_age": {"man", "woman", "boy", "girl", "male", "female", "young", "old", "lady"},
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tokens(text: str) -> set[str]:
    import re
    return set(re.findall(r"[a-z]+", text.lower().replace("t-shirt", "tshirt")))


def attributes(text: str) -> dict[str, set[str]]:
    words = tokens(text)
    return {group: words.intersection(vocabulary) for group, vocabulary in VOCAB.items()}


def score_entry(row: dict) -> tuple[float, dict]:
    source = attributes(str(row["description"]))
    preserved, total = 0, 0
    details = {}
    for index, paraphrase in enumerate(row["paraphrases"]):
        target = attributes(str(paraphrase))
        per_group = {}
        for group in VOCAB:
            expected = source[group]
            if not expected:
                per_group[group] = "not-mentioned"
                continue
            total += 1
            kept = expected.issubset(target[group])
            preserved += int(kept)
            missing = sorted(expected.difference(target[group]))
            per_group[group] = "kept" if kept else "omitted:" + "/".join(missing)
        details[str(index)] = per_group
    return (preserved / total if total else 1.0), details


def image_path(key: str) -> Path:
    normalized = key.replace("\\", "/")
    marker = "datasets/sysu/"
    relative = normalized.split(marker, 1)[1] if marker in normalized else normalized.lstrip("/")
    return DATASET / relative


def choose(payload: dict) -> tuple[list, list]:
    candidates = []
    for key, row in payload.items():
        path = image_path(key)
        if not path.is_file() or len(row.get("paraphrases", [])) != 4:
            continue
        score, details = score_entry(row)
        source_groups = sum(bool(values) for values in attributes(str(row["description"])).values())
        candidates.append(
            {"key": key, "score": score, "source_attribute_groups": source_groups, "details": details}
        )
    high = [item for item in candidates if item["score"] == 1.0 and item["source_attribute_groups"] >= 3]
    difference = [item for item in candidates if item["score"] < 0.75 and item["source_attribute_groups"] >= 2]
    rng = random.Random(SEED)
    selected = rng.sample(high, 4) + rng.sample(difference, 4)
    selected.sort(key=lambda item: (-item["score"], item["key"]))
    return selected, candidates


def wrap(text: str, width: int = 68) -> str:
    import textwrap
    return "\n".join(textwrap.wrap(text, width=width))


def main() -> int:
    os.chdir(REPO)
    sys.path.insert(0, str(REPO))
    from data_loader.dataset import tokenize
    from data_loader.tokenizer import SimpleTokenizer

    payload = json.loads(QWEN_JSON.read_text(encoding="utf-8"))
    generation = json.loads(QWEN_MANIFEST.read_text(encoding="utf-8"))
    selected, candidates = choose(payload)
    OUTPUT.mkdir(parents=True, exist_ok=True)

    with (OUTPUT / "candidate_scores.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=("key", "score", "source_attribute_groups", "selected")
        )
        writer.writeheader()
        chosen_keys = {item["key"] for item in selected}
        for item in candidates:
            writer.writerow(
                {
                    "key": item["key"],
                    "score": f"{item['score']:.6f}",
                    "source_attribute_groups": item["source_attribute_groups"],
                    "selected": item["key"] in chosen_keys,
                }
            )

    device = torch.device("cuda:0")
    model = torch.jit.load(str(CLIP_CHECKPOINT), map_location=device).eval()
    tokenizer = SimpleTokenizer()
    preprocess = transforms.Compose(
        [
            transforms.Resize(224, interpolation=Image.BICUBIC),
            transforms.CenterCrop(224),
            transforms.Lambda(lambda image: image.convert("RGB")),
            transforms.ToTensor(),
            transforms.Normalize(
                (0.48145466, 0.4578275, 0.40821073),
                (0.26862954, 0.26130258, 0.27577711),
            ),
        ]
    )
    torch.cuda.reset_peak_memory_stats(device)
    images = torch.stack([preprocess(Image.open(image_path(item["key"]))) for item in selected]).to(device)
    caption_groups = [
        [str(payload[item["key"]]["description"]), *map(str, payload[item["key"]]["paraphrases"])]
        for item in selected
    ]
    text_tensor = torch.stack(
        [tokenize(text, tokenizer, 77, True) for group in caption_groups for text in group]
    ).to(device)
    with torch.no_grad():
        image_features = model.encode_image(images)
        text_features = model.encode_text(text_tensor)
        image_features /= image_features.norm(dim=-1, keepdim=True)
        text_features /= text_features.norm(dim=-1, keepdim=True)
    similarities = (
        image_features[:, None, :] * text_features.reshape(len(selected), 5, -1)
    ).sum(dim=-1).float().cpu().numpy()

    detail_rows = []
    fig, axes = plt.subplots(
        len(selected), 3, figsize=(15.5, 24.0),
        gridspec_kw={"width_ratios": [1.0, 3.6, 3.6]},
    )
    for row_index, item in enumerate(selected):
        anonymous_id = f"RGBQ-{row_index + 1:02d}"
        row = payload[item["key"]]
        axes[row_index, 0].imshow(Image.open(image_path(item["key"])).convert("RGB"))
        axes[row_index, 0].axis("off")
        axes[row_index, 0].set_title(f"{anonymous_id}\nattribute retention={item['score']:.2f}", fontsize=9)
        axes[row_index, 1].axis("off")
        axes[row_index, 2].axis("off")
        lines = []
        captions = [str(row["description"]), *map(str, row["paraphrases"])]
        for caption_index, caption in enumerate(captions):
            label = "Source" if caption_index == 0 else f"Qwen-{caption_index}"
            lines.append(f"{label}  CLIP={similarities[row_index, caption_index]:.3f}\n{wrap(caption)}")
            detail_rows.append(
                {
                    "anonymous_sample_id": anonymous_id,
                    "image_id": Path(item["key"]).name,
                    "caption_type": label,
                    "caption": caption,
                    "clip_similarity": float(similarities[row_index, caption_index]),
                    "attribute_retention_score": item["score"],
                    "attribute_audit": json.dumps(item["details"], ensure_ascii=False),
                }
            )
        axes[row_index, 1].text(
            0.0, 1.0, "\n\n".join(lines[:3]), ha="left", va="top",
            fontsize=7.3, linespacing=1.18,
        )
        axes[row_index, 2].text(
            0.0, 1.0, "\n\n".join(lines[3:]), ha="left", va="top",
            fontsize=7.3, linespacing=1.18,
        )
    fig.suptitle(
        "RGB source captions and four Qwen paraphrases (fixed stratified audit)", fontsize=13, y=0.995
    )
    fig.text(
        0.5,
        0.003,
        f"Model {generation.get('model')} · revision {generation.get('revision')} · "
        f"prompt {generation.get('prompt_version')} · selection seed {SEED}",
        ha="center",
        fontsize=8,
    )
    fig.tight_layout(rect=(0.02, 0.012, 0.99, 0.99), h_pad=1.8, w_pad=1.4)
    fig.savefig(OUTPUT / "rgb_qwen_caption_audit.png", dpi=300, bbox_inches="tight")
    fig.savefig(OUTPUT / "rgb_qwen_caption_audit.pdf", bbox_inches="tight")
    plt.close(fig)

    with (OUTPUT / "caption_audit_rows.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(detail_rows[0]))
        writer.writeheader()
        writer.writerows(detail_rows)
    script_target = OUTPUT / "make_rgb_caption_panel.py"
    if not script_target.exists():
        try:
            os.link(Path(__file__).resolve(), script_target)
        except OSError:
            shutil.copy2(Path(__file__).resolve(), script_target)
    manifest = {
        "status": "complete",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "selection_rule": "fixed-seed stratified sample: four full-retention and four retention<0.75 cases",
        "selection_seed": SEED,
        "selected_count": len(selected),
        "candidate_count": len(candidates),
        "model": generation.get("model"),
        "model_revision": generation.get("revision"),
        "prompt_version": generation.get("prompt_version"),
        "generation_seed": "per-record seeds retained in Qwen journal; see caption generation metadata",
        "clip_model": "OpenAI CLIP ViT-B/16 zero-shot checkpoint",
        "clip_checkpoint_sha256": sha256(CLIP_CHECKPOINT),
        "qwen_json_sha256": sha256(QWEN_JSON),
        "peak_gpu_memory_bytes": int(torch.cuda.max_memory_allocated(device)),
        "command": "python make_rgb_caption_panel.py",
        "files": {
            name: sha256(OUTPUT / name)
            for name in (
                "candidate_scores.csv", "caption_audit_rows.csv",
                "rgb_qwen_caption_audit.png", "rgb_qwen_caption_audit.pdf",
            )
        },
    }
    (OUTPUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
