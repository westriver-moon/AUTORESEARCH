#!/usr/bin/env python3
"""Extract un-smoothed Stage-II training curves from structured event logs."""

import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_csv(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--seed", required=True)
    ap.add_argument("--selection-rule", required=True)
    ap.add_argument("--replacement-rate", default="not recorded")
    args = ap.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    events = [json.loads(x) for x in args.events.read_text().splitlines() if x.strip()]
    train, evaluation = [], []
    for event in events:
        epoch = event.get("epoch")
        if event.get("event_type") == "train_epoch":
            losses, scalars = event.get("losses", {}), event.get("scalars", {})
            train.append({"epoch": epoch, "id_loss": losses.get("id_loss"),
                          "favta_cross_modal_hard_loss": losses.get("cross_modal_hard_loss"),
                          "total_loss": losses.get("total_loss"), "accuracy": scalars.get("accuracy"),
                          "learning_rate": scalars.get("learning_rate"),
                          "duration_seconds": event.get("duration_seconds"),
                          "replacement_rate": args.replacement_rate})
        elif event.get("event_type") == "eval_epoch":
            metrics = event.get("metrics", {})
            evaluation.append({"epoch": epoch, "rank1": metrics.get("Rank-1"), "mAP": metrics.get("mAP"),
                               "mINP": metrics.get("mINP"), "is_new_best": event.get("is_new_best")})
    train.sort(key=lambda x: x["epoch"]); evaluation.sort(key=lambda x: x["epoch"])
    train_csv = args.output / "train_epochs_unsmoothed.csv"
    eval_csv = args.output / "eval_epochs_unsmoothed.csv"
    write_csv(train_csv, train, list(train[0])); write_csv(eval_csv, evaluation, list(evaluation[0]))

    fig, axes = plt.subplots(1, 2, figsize=(9.0, 3.6), constrained_layout=True)
    epochs = [x["epoch"] for x in train]
    axes[0].plot(epochs, [x["id_loss"] for x in train], marker="o", ms=2.5, label="ID loss")
    axes[0].plot(epochs, [x["favta_cross_modal_hard_loss"] for x in train], marker="s", ms=2.5,
                 label="FAVTA / cross-modal hard")
    axes[0].plot(epochs, [x["total_loss"] for x in train], marker="^", ms=2.5, label="Total")
    axes[0].set(xlabel="Epoch (0-based)", ylabel="Training loss", title="Un-smoothed training losses")
    axes[0].grid(alpha=.25); axes[0].legend(fontsize=7)
    ee = [x["epoch"] for x in evaluation]
    for key, label, marker in (("rank1", "Rank-1", "o"), ("mAP", "mAP", "s"), ("mINP", "mINP", "^")):
        axes[1].plot(ee, [100*x[key] for x in evaluation], marker=marker, ms=2.5, label=label)
    axes[1].set(xlabel="Epoch (0-based; -1 = warm start when present)", ylabel="Metric (%)",
                title="Un-smoothed SYSU all-search evaluation")
    axes[1].grid(alpha=.25); axes[1].legend(fontsize=7)
    fig.suptitle(args.label, fontsize=11)
    png = args.output / "training_and_evaluation_curves.png"; pdf = args.output / "training_and_evaluation_curves.pdf"
    fig.savefig(png, dpi=240, bbox_inches="tight"); fig.savefig(pdf, bbox_inches="tight"); plt.close(fig)

    manifest = {
        "status": "complete", "label": args.label, "seed": args.seed,
        "checkpoint_selection_rule": args.selection_rule, "smoothing": "none",
        "epoch_axis": "0-based training epoch; -1 denotes warm-start evaluation when present",
        "replacement_rate": args.replacement_rate,
        "replacement_rate_note": "not inferred from configured probability" if args.replacement_rate == "not recorded" else None,
        "source_events_sha256": sha256(args.events), "train_epoch_count": len(train), "eval_epoch_count": len(evaluation),
        "files": {p.name: sha256(p) for p in (train_csv, eval_csv, png, pdf)},
    }
    (args.output / "curve_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
