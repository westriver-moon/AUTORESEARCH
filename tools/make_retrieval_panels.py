#!/usr/bin/env python3
"""Render deterministic, auditable Top-10 cross-modal retrieval panels."""

import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load(path):
    with np.load(path, allow_pickle=True) as z:
        return {k: z[k] for k in z.files}


def valid_indices(payload, trial, qi, dataset):
    n = len(payload["gallery_pids"][trial])
    valid = np.ones(n, dtype=bool)
    if dataset == "sysu" and int(payload["query_camids"][qi]) == 3:
        valid &= payload["gallery_camids"][trial] != 2
    return np.flatnonzero(valid)


def order_for(payload, trial, qi, dataset):
    valid = valid_indices(payload, trial, qi, dataset)
    scores = payload["galleries"][trial][valid] @ payload["query"][qi]
    local = np.argsort(-scores, kind="stable")
    return valid[local], scores[local]


def first_correct_rank(payload, trial, qi, dataset):
    order, _ = order_for(payload, trial, qi, dataset)
    pid = int(payload["query_pids"][qi])
    hits = np.flatnonzero(payload["gallery_pids"][trial][order] == pid)
    return int(hits[0] + 1) if len(hits) else 10 ** 9


def relative_id(path, dataset):
    parts = Path(str(path)).parts
    if dataset == "sysu":
        for i, part in enumerate(parts):
            if part.startswith("cam") and i + 2 < len(parts):
                return "/".join(parts[i:i + 3])
    else:
        for i, part in enumerate(parts):
            if part.lower() in ("visible", "thermal") and i + 2 < len(parts):
                return "/".join(parts[i:i + 3])
    return "/".join(parts[-3:])


def display_path(path, sr_root, dataset):
    rel = relative_id(path, dataset)
    if dataset == "sysu":
        candidate = sr_root / "eval" / rel
    else:
        candidate = sr_root / rel
    return candidate if candidate.is_file() else Path(str(path))


def choose_compare(base, final, dataset, seed, count):
    candidates = []
    for trial in range(final["galleries"].shape[0]):
        for qi in range(len(final["query_pids"])):
            br = first_correct_rank(base, trial, qi, dataset)
            fr = first_correct_rank(final, trial, qi, dataset)
            if fr <= 10 and br > fr:
                candidates.append({"trial": trial, "query_index": qi, "pid": int(final["query_pids"][qi]),
                                   "baseline_rank": br, "final_rank": fr, "improvement": br - fr})
    rng = np.random.default_rng(seed)
    rng.shuffle(candidates)
    candidates.sort(key=lambda x: (-x["improvement"], x["final_rank"]))
    selected, seen = [], set()
    for row in candidates:
        if row["pid"] in seen:
            continue
        selected.append(row); seen.add(row["pid"])
        if len(selected) == count:
            break
    return selected, candidates


def choose_single(final, dataset, seed, count):
    candidates = []
    for trial in range(final["galleries"].shape[0]):
        for qi in range(len(final["query_pids"])):
            rank = first_correct_rank(final, trial, qi, dataset)
            if rank <= 10:
                band = "rank1" if rank == 1 else ("rank2_5" if rank <= 5 else "rank6_10")
                candidates.append({"trial": trial, "query_index": qi, "pid": int(final["query_pids"][qi]),
                                   "final_rank": rank, "band": band})
    rng = np.random.default_rng(seed)
    rng.shuffle(candidates)
    target = {"rank1": 2, "rank2_5": 2, "rank6_10": 2}
    selected, seen = [], set()
    for band in ("rank1", "rank2_5", "rank6_10"):
        for row in candidates:
            if row["band"] != band or row["pid"] in seen:
                continue
            selected.append(row); seen.add(row["pid"])
            if sum(x["band"] == band for x in selected) >= target[band]:
                break
    if len(selected) < count:
        for row in candidates:
            if row["pid"] not in seen:
                selected.append(row); seen.add(row["pid"])
            if len(selected) == count:
                break
    return selected[:count], candidates


def draw(selected, methods, paths_payload, dataset, sr_root, title, output, topk):
    rows_per_case = len(methods)
    fig_h = 1.8 * len(selected) * rows_per_case + 0.9
    fig, axes = plt.subplots(len(selected) * rows_per_case, topk + 1,
                             figsize=(2.0 * (topk + 1), fig_h), squeeze=False)
    audit = []
    for case, selection in enumerate(selected):
        qi, trial = selection["query_index"], selection["trial"]
        qpid = int(paths_payload["query_pids"][qi])
        qcam = int(paths_payload["query_camids"][qi]) if "query_camids" in paths_payload else -1
        for method_row, (method_name, payload) in enumerate(methods):
            r = case * rows_per_case + method_row
            qpath = display_path(paths_payload["query_paths"][qi], sr_root, dataset)
            axes[r, 0].imshow(Image.open(qpath).convert("RGB"))
            axes[r, 0].set_title(f"Query\nPID {qpid} · C{qcam}", fontsize=7.5)
            axes[r, 0].set_ylabel(method_name, fontsize=8.5)
            axes[r, 0].set_xticks([]); axes[r, 0].set_yticks([])
            for spine in axes[r, 0].spines.values(): spine.set_visible(False)
            order, scores = order_for(payload, trial, qi, dataset)
            for rank in range(topk):
                gidx, score = int(order[rank]), float(scores[rank])
                gpid = int(payload["gallery_pids"][trial, gidx])
                gcam = int(payload["gallery_camids"][trial, gidx]) if "gallery_camids" in payload else -1
                correct = gpid == qpid
                path = display_path(paths_payload["gallery_paths"][trial, gidx], sr_root, dataset)
                ax = axes[r, rank + 1]
                ax.imshow(Image.open(path).convert("RGB")); ax.set_xticks([]); ax.set_yticks([])
                for spine in ax.spines.values():
                    spine.set_linewidth(2.2); spine.set_edgecolor("#238B45" if correct else "#CB3A31")
                cam_text = f" · C{gcam}" if gcam >= 0 else ""
                ax.set_title(f"#{rank + 1} · {score:.3f}\nPID {gpid}{cam_text}", fontsize=6.7, pad=2)
                audit.append({"case": case + 1, "method": method_name, "trial": trial + 1,
                              "query_index": qi, "query_pid": qpid, "query_cam": qcam,
                              "rank": rank + 1, "similarity": f"{score:.8f}", "gallery_pid": gpid,
                              "gallery_cam": gcam, "correct": correct,
                              "query_image": relative_id(paths_payload["query_paths"][qi], dataset),
                              "gallery_image": relative_id(paths_payload["gallery_paths"][trial, gidx], dataset)})
    fig.suptitle(title, fontsize=13, y=0.998)
    fig.tight_layout(rect=(0, 0, 1, 0.99))
    png = output.with_suffix(".png"); pdf = output.with_suffix(".pdf")
    fig.savefig(png, dpi=220, bbox_inches="tight"); fig.savefig(pdf, bbox_inches="tight"); plt.close(fig)
    return png, pdf, audit


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", choices=("sysu", "regdb"), required=True)
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--final", type=Path, required=True)
    ap.add_argument("--baseline", type=Path)
    ap.add_argument("--sr-root", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--seed", type=int, default=20260731)
    ap.add_argument("--cases", type=int, default=6)
    ap.add_argument("--topk", type=int, default=10)
    args = ap.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    final = load(args.final)
    required = ("query_paths", "gallery_paths")
    if any(k not in final for k in required):
        raise KeyError("Final cache must carry query_paths and gallery_paths")
    if args.baseline:
        base = load(args.baseline)
        for k in ("query_pids", "query_camids", "gallery_pids", "gallery_camids"):
            if not np.array_equal(base[k], final[k]): raise ValueError(f"unaligned {k}")
        selected, candidates = choose_compare(base, final, args.dataset, args.seed, args.cases)
        methods = [("Two-stage baseline", base), ("Final model", final)]
        rule = "top final-model improvements with final correct rank <=10; shuffled before stable improvement sort; unique identities"
    else:
        selected, candidates = choose_single(final, args.dataset, args.seed, args.cases)
        methods = [("Final model", final)]
        rule = "fixed-seed stratified successes: two rank-1, two rank-2..5, two rank-6..10; unique identities"
    if len(selected) != args.cases:
        raise RuntimeError(f"Only selected {len(selected)} of {args.cases} requested cases")
    base_name = f"{args.dataset}_{args.protocol}_top{args.topk}"
    png, pdf, audit = draw(selected, methods, final, args.dataset, args.sr_root, args.title,
                           args.output / base_name, args.topk)
    selected_csv = args.output / "selected_queries.csv"; candidates_csv = args.output / "full_candidate_queries.csv"
    rankings_csv = args.output / "displayed_rankings.csv"
    write_csv(selected_csv, selected); write_csv(candidates_csv, candidates); write_csv(rankings_csv, audit)
    outputs = [png, pdf, selected_csv, candidates_csv, rankings_csv]
    manifest = {
        "status": "complete", "dataset": args.dataset.upper(), "protocol": args.protocol,
        "selection_seed": args.seed, "selection_rule": rule, "selected_case_count": len(selected),
        "candidate_count": len(candidates), "top_k": args.topk,
        "ranking": "cosine similarity on L2-normalized features; stable descending sort",
        "color_key": {"green": "correct identity", "red": "incorrect identity"},
        "source_cache_sha256": sha256(args.final),
        "baseline_cache_sha256": sha256(args.baseline) if args.baseline else None,
        "files": {p.name: sha256(p) for p in outputs},
        "note": "The favorable-case comparison is explicitly illustrative; the complete eligible candidate list is retained for audit.",
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
