#!/usr/bin/env python3
"""Rank every SYSU test caption against its own RGB identity."""

import json
import os
from pathlib import Path
import sys

import numpy as np


CHECKPOINT = Path(
    "/home/lab929/ybj/SALT-VI/checkpoints/stage_b/experiments/"
    "salt_ablation/r_text_visual_20260729/model_output/sysu/FV/"
    "Baseline_train[RGB_IR_Text]_joint[uni]_Blip_parameter_add_id,"
    "cross_modal_hard_Fix_Visual/models/model_Fusion_epoch_23.pth"
)
DATASET_ROOT = Path("/home/cgv841/datasets/SYSU-MM01")
TEXT_ROOT = DATASET_ROOT / "Text"
CAPTION_MAP = TEXT_ROOT / "Blip_RGB" / "id_caption_map_Blip_RGB.json"
CONFIG_RELATIVE = Path("configs/stage_b/r_text_visual_20260729.yaml")


def required_env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError("missing required environment variable: {}".format(name))
    return value


def atomic_write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp.{}".format(os.getpid()))
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(str(temporary), str(path))


def metric_summary(ranks):
    ranks = np.asarray(ranks, dtype=np.float64)
    return {
        "Rank-1": float(np.mean(ranks <= 1)),
        "Rank-5": float(np.mean(ranks <= 5)),
        "Rank-10": float(np.mean(ranks <= 10)),
        "Rank-20": float(np.mean(ranks <= 20)),
        "MRR": float(np.mean(1.0 / ranks)),
        "mean_rank": float(np.mean(ranks)),
        "median_rank": float(np.median(ranks)),
        "p90_rank": float(np.percentile(ranks, 90, interpolation="higher")),
        "p95_rank": float(np.percentile(ranks, 95, interpolation="higher")),
        "best_rank": float(np.min(ranks)),
        "worst_rank": float(np.max(ranks)),
    }


def identity_balanced_summary(ranks, labels):
    labels = np.asarray(labels, dtype=np.int64)
    per_identity = {}
    rows = []
    for pid in sorted(np.unique(labels).tolist()):
        pid_ranks = ranks[labels == pid].reshape(-1)
        summary = metric_summary(pid_ranks)
        summary["caption_count"] = int(np.sum(labels == pid))
        summary["caption_trial_count"] = int(pid_ranks.size)
        per_identity[str(pid)] = summary
        rows.append(summary)
    balanced = {}
    for key in ("Rank-1", "Rank-5", "Rank-10", "Rank-20", "MRR", "mean_rank"):
        balanced[key] = float(np.mean([row[key] for row in rows]))
    balanced["median_identity_mean_rank"] = float(
        np.median([row["mean_rank"] for row in rows])
    )
    balanced["identity_count"] = int(len(rows))
    return balanced, per_identity


def main():
    repo_root = Path(__file__).resolve().parents[2]
    src_root = repo_root / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    config_path = repo_root / CONFIG_RELATIVE
    required = [CHECKPOINT, DATASET_ROOT, TEXT_ROOT, CAPTION_MAP, config_path]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError("missing inputs: {}".format(", ".join(missing)))

    test_ids = [
        int(value)
        for value in (DATASET_ROOT / "exp" / "test_id.txt")
        .read_text(encoding="utf-8")
        .strip()
        .split(",")
    ]
    captions_by_pid = json.loads(CAPTION_MAP.read_text(encoding="utf-8"))
    caption_count = sum(len(captions_by_pid[str(pid)]) for pid in test_ids)
    if len(test_ids) != 96 or caption_count != 6587:
        raise RuntimeError(
            "unexpected test caption contract: ids={}, captions={}".format(
                len(test_ids), caption_count
            )
        )

    if "--validate-only" in sys.argv[1:]:
        print(json.dumps({
            "checkpoint": str(CHECKPOINT),
            "test_identity_count": len(test_ids),
            "test_caption_count": caption_count,
            "gallery_trials": 10,
            "uses_ir_image_features": False,
        }, indent=2, sort_keys=True))
        return 0

    physical_gpu = required_env("AR2_GPU_ID")
    os.environ["CUDA_VISIBLE_DEVICES"] = physical_gpu

    import torch
    from salt_vi.data.dataset import tokenize
    from salt_vi.data.loader import Loader
    from salt_vi.data.tokenizer import SimpleTokenizer
    from salt_vi.engine import build_model
    from salt_vi.engine.test import _eval_image_feature
    from salt_vi.entrypoints.train import (
        _initialize_spatial_backups,
        _load_compatible_state_dict,
    )
    from salt_vi.utils.utils import load_train_configs

    np.random.seed(0)
    torch.manual_seed(0)
    torch.cuda.manual_seed_all(0)

    output_dir = Path(required_env("AR2_OUTPUT_DIR")).resolve()
    results_dir = Path(required_env("AR2_RESULTS_DIR")).resolve()
    config = load_train_configs(str(config_path))
    overrides = {
        "mode": "test",
        "test_modality": "Text",
        "test_model_type": "Fusion",
        "test_model_path": str(CHECKPOINT),
        "output_path": str(output_dir / "all_caption_identity_rank"),
        "CUDA_VISIBLE_DEVICES": physical_gpu,
        "gpu_id": "0",
        "LOG4TEST": True,
        "retrieval_backend": "legacy",
        "sysu_data_path": str(DATASET_ROOT),
        "text_data_root": str(TEXT_ROOT),
        "sysu_sr_modalities": [],
        "sysu_sr_exact_size": False,
        "seed": 0,
        "test_mode": "all",
        "gall_mode": "single",
        "pid_num": 395,
    }
    for key, value in overrides.items():
        setattr(config, key, value)

    device = torch.device("cuda:0")
    loader = Loader(config)
    model = build_model(config).to(device)
    _load_compatible_state_dict(
        model, str(CHECKPOINT), device, preserve_derived_backups=True
    )
    if model._uses_spatial_map_visual() and not hasattr(model, "backup_pool"):
        _initialize_spatial_backups(model, config)
    model.configure_fixed_visual_data_parallel()
    model.set_eval()

    tokenizer = SimpleTokenizer()
    caption_texts = []
    caption_labels = []
    for pid in test_ids:
        for caption in captions_by_pid[str(pid)]:
            caption_texts.append(caption)
            caption_labels.append(pid)
    caption_labels = np.asarray(caption_labels, dtype=np.int64)

    text_features = []
    text_batch_size = 128
    with torch.no_grad():
        for start in range(0, len(caption_texts), text_batch_size):
            batch = torch.stack([
                tokenize(text, tokenizer, text_length=int(config.text_length))
                for text in caption_texts[start:start + text_batch_size]
            ]).to(device)
            feature = model.classifier(model.encode_text_feat(batch), "Text")
            text_features.append(feature.detach().cpu().numpy())
    text_features = np.concatenate(text_features, axis=0)

    all_trial_ranks = []
    trial_gallery_sizes = []
    with torch.no_grad():
        for trial, gallery_loader in enumerate(loader.gallery_loaders):
            gallery_features = []
            for batch_dict in gallery_loader:
                images = batch_dict["img"].to(device)
                feature_map = model.encode_image_featmap(images, "rgb")
                feature = _eval_image_feature(
                    model, feature_map, mode="RGB", use_backup=False
                )
                gallery_features.append(feature.detach().cpu().numpy())
            gallery_features = np.concatenate(gallery_features, axis=0)
            gallery_labels = np.asarray(loader.gallery_labels[trial], dtype=np.int64)
            unique_gallery_ids = np.unique(gallery_labels)
            if set(unique_gallery_ids.tolist()) != set(test_ids):
                raise RuntimeError(
                    "trial {} gallery identity mismatch: {} identities".format(
                        trial, unique_gallery_ids.size
                    )
                )
            trial_gallery_sizes.append(int(gallery_labels.size))
            scores = np.matmul(text_features, gallery_features.T)
            ranks = np.empty(len(caption_labels), dtype=np.int64)
            for query_index, pid in enumerate(caption_labels):
                order = np.argsort(-scores[query_index], kind="stable")
                ordered_labels = gallery_labels[order]
                first = np.unique(ordered_labels, return_index=True)[1]
                ranked_identities = ordered_labels[np.sort(first)]
                match = np.flatnonzero(ranked_identities == pid)
                if match.size != 1:
                    raise RuntimeError(
                        "caption {} pid {} has {} identity matches".format(
                            query_index, pid, match.size
                        )
                    )
                ranks[query_index] = int(match[0]) + 1
            all_trial_ranks.append(ranks)
            print(
                "trial {:02d}: Rank-1={:.6f}, mean-rank={:.4f}".format(
                    trial, np.mean(ranks == 1), np.mean(ranks)
                ),
                flush=True,
            )

    ranks = np.stack(all_trial_ranks, axis=1)
    caption_weighted = metric_summary(ranks.reshape(-1))
    identity_balanced, per_identity = identity_balanced_summary(ranks, caption_labels)
    details = {
        "metrics": {
            "identity_balanced": identity_balanced,
            "caption_weighted": caption_weighted,
            "checkpoint_epoch": 23,
            "selected_gpu": int(physical_gpu),
            "test_identity_count": len(test_ids),
            "test_caption_count": len(caption_texts),
            "gallery_trials": len(all_trial_ranks),
            "gallery_sizes": trial_gallery_sizes,
        },
        "per_identity": per_identity,
        "protocol": {
            "dataset": "SYSU-MM01 test split",
            "query": "all Blip RGB captions of each test identity",
            "gallery": "original RGB images",
            "identity_ranking": "best-scoring gallery image per identity",
            "search": "all-search single-shot 10-trial aggregate",
            "uses_ir_image_features": False,
            "camera_filtering": False,
        },
        "checkpoint": str(CHECKPOINT),
    }
    flat_metrics = {
        "identity_balanced_Rank-1": identity_balanced["Rank-1"],
        "identity_balanced_Rank-5": identity_balanced["Rank-5"],
        "identity_balanced_Rank-10": identity_balanced["Rank-10"],
        "identity_balanced_Rank-20": identity_balanced["Rank-20"],
        "identity_balanced_MRR": identity_balanced["MRR"],
        "identity_balanced_mean_rank": identity_balanced["mean_rank"],
        "caption_weighted_Rank-1": caption_weighted["Rank-1"],
        "caption_weighted_Rank-5": caption_weighted["Rank-5"],
        "caption_weighted_Rank-10": caption_weighted["Rank-10"],
        "caption_weighted_Rank-20": caption_weighted["Rank-20"],
        "caption_weighted_MRR": caption_weighted["MRR"],
        "caption_weighted_mean_rank": caption_weighted["mean_rank"],
        "caption_weighted_median_rank": caption_weighted["median_rank"],
        "caption_weighted_p90_rank": caption_weighted["p90_rank"],
        "caption_weighted_p95_rank": caption_weighted["p95_rank"],
        "test_identity_count": float(len(test_ids)),
        "test_caption_count": float(len(caption_texts)),
        "gallery_trials": float(len(all_trial_ranks)),
        "checkpoint_epoch": 23.0,
        "selected_gpu": float(physical_gpu),
    }
    atomic_write_json(results_dir / "metrics.json", {
        "primary_metric": identity_balanced["Rank-1"],
        "metrics": flat_metrics,
    })
    atomic_write_json(output_dir / "caption_identity_rank_details.json", details)
    print(json.dumps(details["metrics"], indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("caption identity-rank evaluation failed: {}".format(exc), file=sys.stderr)
        raise
