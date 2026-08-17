#!/usr/bin/env python3
"""Export reproducible final-model retrieval caches for supplementary panels.

The script performs evaluation only. It never trains, overwrites a checkpoint,
or modifies the source experiment. The saved features are L2-normalized so the
reported dot products are cosine similarities.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--dataset", required=True, choices=("sysu", "regdb"))
    parser.add_argument("--protocol", required=True, choices=("all", "indoor", "t-v"))
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--seed", default=0, type=int)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def l2(value: np.ndarray) -> np.ndarray:
    value = np.asarray(value, dtype=np.float32)
    return value / np.clip(np.linalg.norm(value, axis=1, keepdims=True), 1e-12, None)


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def decode_captions(dataset) -> np.ndarray:
    from data_loader.dataset import SimpleTokenizer

    tokenizer = SimpleTokenizer()
    captions = []
    for tokens in dataset.test_text_rgb:
        ids = [int(item) for item in torch.as_tensor(tokens).flatten().tolist() if int(item) != 0]
        text = tokenizer.decode(ids)
        text = text.replace("<|startoftext|>", "").replace("<|endoftext|>", "").strip()
        captions.append(text)
    return np.asarray(captions, dtype=np.str_)


def extract_query(model, loader, device: torch.device):
    parts = []
    captions = decode_captions(loader.dataset)
    model.set_eval()
    with torch.no_grad():
        for batch in loader:
            images = batch["img"].to(device, non_blocking=True)
            text = batch["text"].to(device, non_blocking=True).long()
            raw = model.encode_fusion(text, images, "ir")
            feature = model.classifier(raw, "Fusion")
            parts.append(feature.detach().float().cpu().numpy())
    return l2(np.concatenate(parts, axis=0)), captions


def extract_gallery(model, loader, device: torch.device) -> np.ndarray:
    parts = []
    model.set_eval()
    with torch.no_grad():
        for batch in loader:
            images = batch["img"].to(device, non_blocking=True)
            fmap = model.encode_image_featmap(images, "rgb")
            raw = model.extract_global_feat(fmap)
            feature = model.classifier(raw, "RGB")
            parts.append(feature.detach().float().cpu().numpy())
    return l2(np.concatenate(parts, axis=0))


def main() -> int:
    args = parse_args()
    args.repo = args.repo.resolve()
    args.config = args.config.resolve()
    args.checkpoint = args.checkpoint.resolve()
    args.output = args.output.resolve()
    for path in (args.repo / "main.py", args.config, args.checkpoint):
        if not path.is_file():
            raise FileNotFoundError(path)
    if args.dataset == "sysu" and args.protocol not in {"all", "indoor"}:
        raise ValueError("SYSU protocol must be all or indoor")
    if args.dataset == "regdb" and args.protocol != "t-v":
        raise ValueError("RegDB supplementary cache is Thermal-to-Visible")

    # The historical tokenizer resolves its BPE vocabulary relative to the
    # repository working directory, so evaluation must run from that root.
    os.chdir(args.repo)
    sys.path.insert(0, str(args.repo))
    from core import build_model
    from data_loader.dataset import process_gallery_sysu, process_query_sysu, process_test_regdb
    from data_loader.loader import Loader
    from scripts.metric_boost.eval_engine import load_model_checkpoint
    from tools.utils import load_train_configs

    seed_everything(args.seed)
    config = load_train_configs(str(args.config))
    config.mode = "test"
    config.dataset = args.dataset
    config.test_modality = "Fusion"
    config.DataParallel = False
    config.fixed_visual_data_parallel = False
    config.fixed_visual_device_ids = [0]
    config.num_workers = min(2, int(getattr(config, "num_workers", 2)))
    config.test_batch_size = min(8, int(getattr(config, "test_batch_size", 8)))
    config.CAT_EVAL = False
    config.test_flip_tta = False
    config.rerank = False
    config.llm_aug = False
    if args.dataset == "sysu":
        config.pid_num = 395
        config.test_mode = args.protocol
        config.gall_mode = "single"
        config.gallery_trials = 10
    else:
        config.regdb_test_mode = "t-v"
        config.eval_num_regdb = 1

    device = torch.device(args.device)
    if device.type != "cuda" or not torch.cuda.is_available():
        raise RuntimeError("A leased CUDA GPU is required")
    torch.cuda.set_device(device)
    torch.cuda.reset_peak_memory_stats(device)
    start = time.perf_counter()

    loader = Loader(config)
    model = build_model(config)
    load_audit = load_model_checkpoint(
        model, args.checkpoint, source_size=(int(config.img_h), int(config.img_w))
    )
    model = model.to(device).eval()

    if args.dataset == "sysu":
        query_loader = loader.query_loader
        query_features, captions = extract_query(model, query_loader, device)
        gallery_features = [extract_gallery(model, item, device) for item in loader.gallery_loaders]
        query_paths, query_pids, query_camids = process_query_sysu(
            config.sysu_data_path, mode=args.protocol
        )
        gallery_paths, gallery_pids, gallery_camids = [], [], []
        for trial in range(10):
            paths, pids, cams = process_gallery_sysu(
                config.sysu_data_path, mode=args.protocol, trial=trial, gall_mode="single"
            )
            gallery_paths.append(np.asarray(paths, dtype=np.str_))
            gallery_pids.append(np.asarray(pids, dtype=np.int64))
            gallery_camids.append(np.asarray(cams, dtype=np.int64))
        query_camids = np.asarray(query_camids, dtype=np.int64)
        gallery_features_array = np.stack(gallery_features)
        gallery_paths_array = np.stack(gallery_paths)
        gallery_pids_array = np.stack(gallery_pids)
        gallery_camids_array = np.stack(gallery_camids)
    else:
        query_loader = loader.query_loaders[0]
        query_features, captions = extract_query(model, query_loader, device)
        gallery_features_array = extract_gallery(model, loader.gallery_loaders[0], device)[None, ...]
        query_paths, query_pids = process_test_regdb(
            config.regdb_data_path, trial=int(config.trial), modal="thermal"
        )
        gallery_paths_one, gallery_pids_one = process_test_regdb(
            config.regdb_data_path, trial=int(config.trial), modal="visible"
        )
        query_camids = np.full(len(query_pids), -1, dtype=np.int64)
        gallery_paths_array = np.asarray(gallery_paths_one, dtype=np.str_)[None, ...]
        gallery_pids_array = np.asarray(gallery_pids_one, dtype=np.int64)[None, ...]
        gallery_camids_array = np.full(gallery_pids_array.shape, -1, dtype=np.int64)

    elapsed = time.perf_counter() - start
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.output,
        query=query_features,
        query_pids=np.asarray(query_pids, dtype=np.int64),
        query_camids=query_camids,
        query_paths=np.asarray(query_paths, dtype=np.str_),
        query_captions=captions,
        galleries=gallery_features_array,
        gallery_pids=gallery_pids_array,
        gallery_camids=gallery_camids_array,
        gallery_paths=gallery_paths_array,
    )
    source_commit = subprocess.check_output(
        ["git", "-C", str(args.repo), "rev-parse", "HEAD"], text=True
    ).strip()
    manifest = {
        "status": "complete",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "operation": "evaluation-only feature extraction; no training",
        "dataset": args.dataset,
        "protocol": args.protocol,
        "seed": args.seed,
        "source_commit": source_commit,
        "source_clean": not bool(
            subprocess.check_output(
                ["git", "-C", str(args.repo), "status", "--short"], text=True
            ).strip()
        ),
        "config_sha256": sha256(args.config),
        "checkpoint_sha256": sha256(args.checkpoint),
        "checkpoint_load_audit": load_audit,
        "cache_sha256": sha256(args.output),
        "device_name": torch.cuda.get_device_name(device),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES", "not-set"),
        "peak_allocated_bytes": int(torch.cuda.max_memory_allocated(device)),
        "peak_reserved_bytes": int(torch.cuda.max_memory_reserved(device)),
        "elapsed_seconds": elapsed,
        "query_count": int(len(query_features)),
        "gallery_trials": int(len(gallery_features_array)),
        "gallery_count_per_trial": [int(len(item)) for item in gallery_features_array],
        "similarity": "cosine (L2-normalized feature dot product)",
        "command": " ".join(sys.argv),
    }
    manifest_path = args.output.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
