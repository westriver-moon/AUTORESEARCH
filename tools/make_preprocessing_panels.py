#!/usr/bin/env python3
"""Build deterministic raw/loader/SwinIR and token-grid evidence panels."""

import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from PIL import Image


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def sysu_samples(raw_root, sr_root):
    ids = [x.strip() for x in (raw_root / "exp/test_id.txt").read_text().split(",") if x.strip()]
    out = []
    for pid in sorted(ids, key=int):
        pid4 = f"{int(pid):04d}"
        chosen = []
        for modality, cams in (("RGB", ("cam1", "cam2", "cam4", "cam5")), ("IR", ("cam3", "cam6"))):
            found = None
            for cam in cams:
                candidates = sorted((raw_root / cam / pid4).glob("*.jpg"))
                for raw in candidates:
                    sr = sr_root / "eval" / cam / pid4 / raw.name
                    if sr.exists():
                        found = (pid4, modality, raw, sr, f"{cam}/{pid4}/{raw.name}")
                        break
                if found:
                    break
            if found:
                chosen.append(found)
        if len(chosen) == 2:
            out.extend(chosen)
        if len(out) == 4:
            break
    return out


def regdb_samples(raw_root, sr_root):
    out = []
    shared = sorted(
        set(x.name for x in (raw_root / "Visible").iterdir() if x.is_dir())
        & set(x.name for x in (raw_root / "Thermal").iterdir() if x.is_dir()),
        key=int,
    )
    for pid in shared:
        chosen = []
        for modality, folder in (("RGB", "Visible"), ("IR", "Thermal")):
            found = None
            for raw in sorted((raw_root / folder / pid).glob("*.bmp")):
                sr = sr_root / folder / pid / raw.name
                if sr.exists():
                    found = (pid, modality, raw, sr, f"{folder}/{pid}/{raw.name}")
                    break
            if found:
                chosen.append(found)
        if len(chosen) == 2:
            out.extend(chosen)
        if len(out) == 4:
            break
    return out


def loader_image(raw):
    image = Image.open(raw).convert("RGB")
    return image.resize((128, 256), Image.Resampling.BILINEAR)


def draw_grid(ax, image, patch_hw, stride_hw, title):
    ax.imshow(image)
    h, w = image.height, image.width
    ph, pw = patch_hw
    sh, sw = stride_hw
    count = 0
    for y in range(0, h - ph + 1, sh):
        for x in range(0, w - pw + 1, sw):
            ax.add_patch(Rectangle((x, y), pw, ph, fill=False, edgecolor="#00AEEF", linewidth=0.25, alpha=0.65))
            count += 1
    ax.set_title(f"{title}\n{ph}x{pw}, stride {sh}x{sw} ({count} tokens)", fontsize=8)
    ax.axis("off")
    return count


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", choices=("sysu", "regdb"), required=True)
    ap.add_argument("--raw-root", type=Path, required=True)
    ap.add_argument("--sr-root", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    manifest_path = args.sr_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    samples = sysu_samples(args.raw_root, args.sr_root) if args.dataset == "sysu" else regdb_samples(args.raw_root, args.sr_root)
    if len(samples) != 4:
        raise RuntimeError(f"Expected four deterministic RGB/IR samples, got {len(samples)}")

    fig, axes = plt.subplots(4, 3, figsize=(7.2, 13.2), constrained_layout=True)
    rows = []
    for i, (pid, modality, raw_path, sr_path, rel) in enumerate(samples):
        raw = Image.open(raw_path).convert("RGB")
        loader = loader_image(raw_path)
        sr = Image.open(sr_path).convert("RGB")
        for ax, image, title in zip(
            axes[i],
            (raw, loader, sr),
            (f"Raw ({raw.height}x{raw.width})", "Loader source (256x128)", "Fixed SwinIR x2 (512x256)"),
        ):
            ax.imshow(image)
            ax.set_title(title, fontsize=9)
            ax.axis("off")
        axes[i, 0].set_ylabel(f"ID {pid} / {modality}", fontsize=9)
        rows.append({
            "dataset": args.dataset.upper(), "identity": pid, "modality": modality,
            "relative_image": rel, "raw_height": raw.height, "raw_width": raw.width,
            "loader_height": loader.height, "loader_width": loader.width,
            "sr_height": sr.height, "sr_width": sr.width,
            "raw_sha256": sha256(raw_path), "sr_sha256": sha256(sr_path),
        })
    panel_png = args.output / f"{args.dataset}_raw_loader_swinir_panel.png"
    panel_pdf = args.output / f"{args.dataset}_raw_loader_swinir_panel.pdf"
    fig.savefig(panel_png, dpi=220, bbox_inches="tight")
    fig.savefig(panel_pdf, bbox_inches="tight")
    plt.close(fig)

    example = Image.open(samples[0][3]).convert("RGB")
    fig, axes = plt.subplots(1, 2, figsize=(6.0, 6.2), constrained_layout=True)
    anchor_count = draw_grid(axes[0], example, (16, 16), (12, 12), "Anchor grid")
    fine_count = draw_grid(axes[1], example, (16, 8), (12, 6), "Fine-grained grid")
    grid_png = args.output / f"{args.dataset}_anchor_vs_fine_token_grid.png"
    grid_pdf = args.output / f"{args.dataset}_anchor_vs_fine_token_grid.pdf"
    fig.savefig(grid_png, dpi=240, bbox_inches="tight")
    fig.savefig(grid_pdf, bbox_inches="tight")
    plt.close(fig)

    csv_path = args.output / "selected_samples.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)

    model_hash = manifest.get("build_identity", {}).get("model_sha256") or manifest.get("model_sha256")
    report = {
        "status": "complete", "dataset": args.dataset.upper(),
        "selection_rule": "first two sorted identities having both RGB and IR with matching fixed-SR outputs",
        "sample_count": 4, "loader_source_size_hw": [256, 128], "sr_output_size_hw": [512, 256],
        "source_resampling": manifest.get("source_resampling", "bilinear"),
        "super_resolution_algorithm": manifest.get("algorithm"), "super_resolution_model_sha256": model_hash,
        "ir_policy": manifest.get("ir_policy"),
        "token_grids": {
            "anchor": {"patch_hw": [16, 16], "stride_hw": [12, 12], "token_count": anchor_count},
            "fine": {"patch_hw": [16, 8], "stride_hw": [12, 6], "token_count": fine_count},
        },
        "files": {p.name: sha256(p) for p in (panel_png, panel_pdf, grid_png, grid_pdf, csv_path)},
        "note": "Raw images are used only as deterministic evidence examples; training consumes the fixed loader/SR representations documented here.",
    }
    (args.output / "manifest.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
