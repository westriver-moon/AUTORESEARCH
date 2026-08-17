#!/usr/bin/env python3
"""Finalize the consolidated non-multi-seed AAAI-27 evidence package."""

import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_csv(path):
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields=None):
    if not rows: return
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields or list(rows[0])); w.writeheader(); w.writerows(rows)


def json_load(path):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return {}


def add_stage1_manifest(root):
    d = root / "visual_evidence/training_curves/stage1"
    files = [d / "mbpatch_train_metrics.csv", d / "mbpatch_eval_metrics.csv"]
    manifest = {
        "status": "complete", "seed": 0, "smoothing": "none",
        "checkpoint_selection_rule": "best Rank-1 checkpoint at epoch 27 for this recorded 30-epoch run",
        "epoch_axis": "0-based epoch; evaluation every two epochs",
        "progressive_mixing_coefficient": "configured progressive_epoch=6; per-epoch coefficient not recorded in exported CSV",
        "loss_columns": {"id": "id_loss", "triplet": "tri_loss", "msct_components": ["msel_loss", "dcl_loss"]},
        "peak_gpu_memory": "not recorded", "source_commit": "not recorded in this legacy curve archive",
        "files": {p.name: sha256(p) for p in files if p.exists()},
    }
    (d / "curve_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")


def regdb_trial_plot(root):
    source = root / "final_runtime_records/regdb_final_10trials.csv"
    rows = read_csv(source)
    trials = [int(x["official_trial"]) for x in rows]
    metrics = {"Rank-1": [100*float(x["rank1"]) for x in rows],
               "mAP": [100*float(x["map"]) for x in rows],
               "mINP": [100*float(x["minp"]) for x in rows]}
    out = root / "visual_evidence/regdb_trial_variation"; out.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7.2, 3.8), constrained_layout=True)
    for label, values, marker in (("Rank-1", metrics["Rank-1"], "o"), ("mAP", metrics["mAP"], "s"),
                                  ("mINP", metrics["mINP"], "^")):
        ax.plot(trials, values, marker=marker, label=f"{label} (mean {np.mean(values):.2f})")
        ax.axhline(np.mean(values), linewidth=.8, alpha=.25)
    ax.set(xlabel="Official RegDB trial", ylabel="Metric (%)", xticks=trials,
           title="RegDB thermal-to-visible variation across 10 official trials")
    ax.grid(alpha=.22); ax.legend(ncol=3, fontsize=7)
    png = out / "regdb_10trial_scatter.png"; pdf = out / "regdb_10trial_scatter.pdf"
    fig.savefig(png, dpi=240, bbox_inches="tight"); fig.savefig(pdf, bbox_inches="tight"); plt.close(fig)
    manifest = {"status": "complete", "source_csv_sha256": sha256(source), "seed": "official trial definitions; model seed 0",
                "aggregation": "arithmetic mean over the ten selected per-trial checkpoints",
                "means_percent": {k: float(np.mean(v)) for k,v in metrics.items()},
                "files": {p.name: sha256(p) for p in (png,pdf)}}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def resource_report(root):
    def man(rel): return json_load(root / rel)
    all_m = man("visual_evidence/retrieval_panels/sysu_all/retrieval_cache_sysu_all.manifest.json")
    indoor_m = man("visual_evidence/retrieval_panels/sysu_indoor/retrieval_cache_sysu_indoor.manifest.json")
    regdb_m = man("visual_evidence/retrieval_panels/regdb_tv/retrieval_cache_regdb_trial04_tv.manifest.json")
    rows = [
        {"phase":"SYSU Stage-I training","dataset":"SYSU","total_parameters":151665665,"trainable_parameters":88106497,
         "parameter_provenance":"checkpoint tensor count; trainable inferred from freeze_text_in_image_only=true",
         "peak_allocated_bytes":"not recorded","elapsed_seconds":16608,"batch_size":32,"flops":"not computed"},
        {"phase":"SYSU Stage-II training","dataset":"SYSU","total_parameters":151665664,"trainable_parameters":63864064,
         "parameter_provenance":"direct model build report","peak_allocated_bytes":"not recorded","elapsed_seconds":18188,
         "batch_size":8,"flops":"not computed"},
        {"phase":"SYSU all-search inference","dataset":"SYSU","total_parameters":151665664,"trainable_parameters":63864064,
         "parameter_provenance":"direct model build report","peak_allocated_bytes":all_m.get("peak_allocated_bytes","not recorded"),
         "elapsed_seconds":all_m.get("elapsed_seconds","not recorded"),"batch_size":8,"flops":"not computed"},
        {"phase":"SYSU indoor-search inference","dataset":"SYSU","total_parameters":151665664,"trainable_parameters":63864064,
         "parameter_provenance":"direct model build report","peak_allocated_bytes":indoor_m.get("peak_allocated_bytes","not recorded"),
         "elapsed_seconds":indoor_m.get("elapsed_seconds","not recorded"),"batch_size":8,"flops":"not computed"},
        {"phase":"RegDB Trial-4 T-V inference","dataset":"RegDB","total_parameters":151520512,"trainable_parameters":63718912,
         "parameter_provenance":"direct model build report","peak_allocated_bytes":regdb_m.get("peak_allocated_bytes","not recorded"),
         "elapsed_seconds":regdb_m.get("elapsed_seconds","not recorded"),"batch_size":8,"flops":"not computed"},
    ]
    out = root / "resource_statistics"; out.mkdir(exist_ok=True)
    write_csv(out / "resource_statistics.csv", rows)
    notes = """# Resource statistics notes

- Training peak GPU memory was not present in the original logs and is reported as `not recorded`.
- Inference memory is `torch.cuda.max_memory_allocated()` from the lightweight feature export; elapsed time includes model load and feature extraction.
- Stage-I trainable count is explicitly an inference from the saved checkpoint plus `freeze_text_in_image_only=true`; Stage-II counts come from the model's runtime report.
- FLOPs are `not computed` because no validated FLOP counter exists for this multi-branch, multi-modal execution path.
"""
    (out / "README.md").write_text(notes, encoding="utf-8")


def checkpoint_inventory(root):
    sysu, regdb = read_csv(root / "checkpoint_inventory_3090.csv"), read_csv(root / "checkpoint_inventory_regdb.csv")
    rows = []
    for x in sysu:
        rows.append({"checkpoint_id":x["checkpoint_id"],"dataset":x["dataset"],"role":x["role"],
                     "official_trial":"","selected_epoch":"","filename":x["filename"],"exists_on_source_server":x["exists"],
                     "size_bytes":x["size_bytes"],"sha256":x["sha256"],"included_in_3090_export":"yes"})
    for x in regdb:
        rows.append({"checkpoint_id":x["checkpoint_id"],"dataset":x["dataset"],"role":"selected highest-mAP checkpoint",
                     "official_trial":x["official_trial"],"selected_epoch":x["selected_epoch"],"filename":x["filename"],
                     "exists_on_source_server":x["exists"],"size_bytes":x["size_bytes"],"sha256":x["sha256"],
                     "included_in_3090_export":"no; retained and checksum-verified on 4090"})
    write_csv(root / "checkpoint_inventory.csv", rows)


def query_ids(path):
    if not path.exists(): return ""
    rows=read_csv(path)
    return ";".join(f"t{x.get('trial','')}:q{x.get('query_index','')}:pid{x.get('pid','')}" for x in rows)


def figure_manifest(root):
    sysu_commit="933c055e2bb1b1e2495065bd8b0c64174bc63f53"; regdb_commit="c476f51f92aeec9a62e80454608dc25ba1417991"
    sysu_ckpt="a1c3747e86d18b0700c0f0101c05caadd9f52711ef30d705be6e897e8b60303f"
    regdb_ckpt="00485659bd35efc2f3781c6a37d592a526f3a8f25024975f02d1f1f96b79097d"
    script_retr=root/"tools/make_retrieval_panels.py"; script_pre=root/"tools/make_preprocessing_panels.py"
    script_curve=root/"tools/make_training_curve_evidence.py"
    entries=[]
    def add(fid,dataset,protocol,qids,commit,config,ckpt,data,script,command,seed,status="complete"):
        entries.append({"figure_id":fid,"dataset":dataset,"protocol":protocol,"query_ids":qids,
                        "source_commit":commit,"config_sha256":config,"checkpoint_sha256":ckpt,
                        "data_sha256":sha256(data) if isinstance(data,Path) and data.exists() else str(data),
                        "script_sha256":sha256(script) if script.exists() else "not recorded",
                        "command_sha256":hashlib.sha256(command.encode()).hexdigest(),"seed":seed,"status":status})
    for protocol,sub in (("all-search","sysu_all"),("indoor-search","sysu_indoor")):
        d=root/f"visual_evidence/retrieval_panels/{sub}"; cache=next(d.glob("retrieval_cache*.npz"))
        add(f"retrieval_{sub}","SYSU",protocol,query_ids(d/"selected_queries.csv"),sysu_commit,"see cache manifest",sysu_ckpt,
            cache,script_retr,f"make_retrieval_panels {sub}",20260731)
    d=root/"visual_evidence/retrieval_panels/regdb_tv"; cache=d/"retrieval_cache_regdb_trial04_tv.npz"
    add("retrieval_regdb_tv","RegDB","Trial-4 thermal-to-visible",query_ids(d/"selected_queries.csv"),regdb_commit,
        "dab1b13652f6d59102c6d81eb59bad9defc473a79af9037dc01035cfc3131f0c",regdb_ckpt,cache,script_retr,
        "make_retrieval_panels regdb trial04 t-v",20260731)
    for ds,commit in (("sysu",sysu_commit),("regdb",regdb_commit)):
        d=root/f"visual_evidence/preprocessing/{ds}"
        for kind in ("raw_loader_swinir_panel","anchor_vs_fine_token_grid"):
            png=next(d.glob(f"*{kind}.png")); add(f"preprocessing_{ds}_{kind}",ds.upper(),"preprocessing","",commit,
                "not applicable","not applicable",d/"selected_samples.csv",script_pre,f"make_preprocessing_panels {ds} {kind}","deterministic")
    d=root/"visual_evidence/caption_panels/rgb_qwen_generation"
    add("rgb_qwen_caption_audit","SYSU","RGB caption generation","8 fixed audit images",sysu_commit,"not applicable",
        "CLIP audit checkpoint 5806e77c...",d/"caption_audit_rows.csv",root/"tools/make_rgb_caption_panel.py","make_rgb_caption_panel",20260731)
    for sub,label in (("stage2_8365","stage2_8365"),("stage2_qwen_seed0","stage2_qwen_seed0")):
        d=root/f"visual_evidence/training_curves/{sub}"
        add(f"training_{label}","SYSU","all-search training curve","",sysu_commit,"see runtime config",sysu_ckpt,
            d/"eval_epochs_unsmoothed.csv",script_curve,f"make_training_curve_evidence {sub}",0)
    d=root/"visual_evidence/regdb_trial_variation"
    add("regdb_10trial_scatter","RegDB","10 official trials","trials 1-10",regdb_commit,"per-trial hashes in CSV",
        "per-trial hashes in CSV",root/"final_runtime_records/regdb_final_10trials.csv",Path(__file__),"regdb_trial_plot",0)
    write_csv(root/"visual_evidence/FIGURE_MANIFEST.csv",entries)


def write_readme(root):
    text="""# AAAI-27 server evidence export (non-multi-seed scope)

This package consolidates the requested server evidence while **explicitly excluding all SYSU multi-seed experiments** by user decision. No multi-seed job was launched.

## Core contents

- `final_regdb_source/`: anonymous exact source snapshot at commit `c476f51...`.
- `final_runtime_records/`: ten official RegDB trial configs, commands, selected events, checkpoint records, and independent recomputation.
- `caption_manifests/`: source/Qwen caption inventories, structural validation, generation metadata, and BCC sampling trace.
- `visual_evidence/`: retrieval, preprocessing/token grids, caption audits, representation diagnostics, and unsmoothed training curves.
- `environment_snapshots/`: sanitized 3090 and 4090 software/hardware records.
- `checkpoint_inventory.csv`: existence, size, hashes, and preservation location. Four representative SYSU checkpoints are included; RegDB checkpoints remain checksum-verified on the 4090 source server.
- `resource_statistics/`: parameter, memory, and timing evidence with missing fields marked `not recorded`.

## Important metric finding

The independently recomputed ten-trial RegDB mean is Rank-1 **88.7961%**, mAP **82.7290%**, mINP **68.6410%**. The previously supplied 90.7282/84.5314/70.9206 values match **Trial 4**, not the ten-trial mean; the export preserves this mismatch instead of relabeling it.

## Deliberate exclusions and limitations

- SYSU multi-seed: excluded; no jobs or synthetic summary.
- Actual RGB-caption replacement rate: not logged; `p=0.5` is configuration only and is not reported as an observed rate.
- Training peak GPU memory and FLOPs: not recorded / not computed.
- Dataset raw images are not redistributed; panels retain anonymous relative IDs and reproducible plotting scripts.
"""
    (root/"README.md").write_text(text,encoding="utf-8")
    status="""# Requirement completion matrix

| Requirement | Status | Evidence |
|---|---|---|
| Exact RegDB source commit | Complete | `final_regdb_source/` |
| RegDB 10 official trials | Complete; supplied aggregate mismatch documented | `final_runtime_records/` |
| SYSU multi-seed | Excluded by user decision | No experiment launched |
| Caption manifests and validation | Complete | `caption_manifests/` |
| Environment/hardware | Complete | `environment_snapshots/` |
| Checkpoint inventory | Complete | `checkpoint_inventory.csv` |
| SYSU all / indoor / RegDB T-V Top-10 | Complete | `visual_evidence/retrieval_panels/` |
| SYSU and RegDB preprocessing + token grids | Complete | `visual_evidence/preprocessing/` |
| RGB-Qwen / BCC / inherited IR audit | Complete | `visual_evidence/caption_panels/` |
| Representation diagnostics | Reused existing checkpoint-backed evidence | `visual_evidence/representation_diagnostics/` and `existing_sysu_package/` |
| Training curves | Complete for logged fields; missing fields marked | `visual_evidence/training_curves/` |
| Resource statistics | Complete for reliable records | `resource_statistics/` |
"""
    (root/"REQUIREMENT_STATUS.md").write_text(status,encoding="utf-8")


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--root",type=Path,required=True); args=ap.parse_args()
    add_stage1_manifest(args.root); regdb_trial_plot(args.root); resource_report(args.root)
    checkpoint_inventory(args.root); write_readme(args.root); figure_manifest(args.root)
    (args.root/"SCOPE_DECISION.json").write_text(json.dumps({"sysu_multiseed":"excluded by user decision",
        "jobs_launched":0,"artifacts_created":0,"priority":"all other requirements"},indent=2)+"\n")
    print(json.dumps({"status":"finalized","root":str(args.root),"multiseed":"excluded"},indent=2))


if __name__=="__main__": main()
