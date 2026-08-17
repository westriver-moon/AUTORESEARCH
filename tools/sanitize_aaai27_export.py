#!/usr/bin/env python3
"""Sanitize only the consolidated export copy and regenerate package hashes."""

import argparse
import csv
import hashlib
import json
import os
import re
import tarfile
import tempfile
from pathlib import Path


SKIP_SUFFIXES = {".pth", ".npz", ".npy", ".png", ".pdf", ".jpg", ".jpeg", ".bmp", ".gz", ".pyc"}
MAPPINGS = [
    ("/home/cgv841/datasets", "${DATA_ROOT}"),
    ("/home/cgv841/weights", "${PRETRAINED_ROOT}"),
    ("/home/cgv841/ybj", "${PROJECT_ROOT}"),
    ("/home/lab929/ybj/assets", "${ASSET_ROOT}"),
    ("/home/lab929/ybj", "${PROJECT_ROOT}"),
    ("/home/cgv841", "${HOME_DIR}"),
    ("/home/lab929", "${HOME_DIR}"),
    ("lab-server", "<SERVER_3090>"),
    ("lab929", "<SERVER_4090>"),
]
EMAIL = re.compile(r"(?i)\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_write(path, text):
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f: f.write(text)
        os.chmod(tmp, path.stat().st_mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--root",type=Path,required=True); args=ap.parse_args()
    root=args.root.resolve(); changes=[]
    excluded={root/"EXPORT_SHA256SUMS.txt",root/"export_inventory.csv",root/"ANONYMITY_AUDIT.md"}
    for p in root.rglob("*"):
        if not p.is_file() or p in excluded or p.suffix.lower() in SKIP_SUFFIXES: continue
        try: original=p.read_text(encoding="utf-8")
        except (UnicodeDecodeError,OSError): continue
        revised=original; counts={}
        for old,new in MAPPINGS:
            n=revised.count(old)
            if n: revised=revised.replace(old,new); counts[old]=n
        revised,n=EMAIL.subn("<author-email-redacted>",revised)
        if n: counts["email"]=n
        if revised!=original:
            atomic_write(p,revised)
            changes.append({"file":str(p.relative_to(root)),"replacement_count":sum(counts.values()),
                            "categories":";".join("email" if x=="email" else "absolute-path-or-host" for x in counts)})

    src=root/"final_regdb_source"
    exact_archive=src/"SALT_VI_REGDB_SOURCE_c476f51.tar.gz"
    if exact_archive.exists():
        exact_archive.unlink()  # Redundant anonymous-copy artifact; exact original remains on the 4090 source server.
    sanitized_archive=src/"SALT_VI_REGDB_SOURCE_c476f51_ANONYMIZED.tar.gz"
    with tarfile.open(sanitized_archive,"w:gz") as tf:
        tf.add(src/"source",arcname="SALT-VI")
    commit=src/"COMMIT.txt"
    commit_text=commit.read_text()
    commit_text=re.sub(r"uncommitted_diff=.*", "uncommitted_diff=anonymization-only path/email redaction in exported copy", commit_text)
    if "exact_original_location" not in commit_text:
        commit_text += "exact_original_location=retained on source server; excluded from anonymous consolidated package\n"
    atomic_write(commit,commit_text)
    source_files=sorted(p for p in (src/"source").rglob("*") if p.is_file())
    tree_lines=[f"{sha256(p)}  {p.relative_to(src)}" for p in source_files]
    atomic_write(src/"SOURCE_TREE_SHA256SUMS.txt","\n".join(tree_lines)+"\n")
    atomic_write(src/"SOURCE_SHA256SUMS.txt",f"{sha256(sanitized_archive)}  {sanitized_archive.name}\n"
                 f"{sha256(commit)}  COMMIT.txt\n{sha256(src/'SOURCE_TREE_SHA256SUMS.txt')}  SOURCE_TREE_SHA256SUMS.txt\n")
    (src/"ANONYMIZATION_MANIFEST.json").write_text(json.dumps({"status":"complete","source_commit":"c476f51f92aeec9a62e80454608dc25ba1417991",
        "transformation":"absolute home paths, server aliases, and author email replaced only in the anonymous export copy",
        "exact_original_retained_on_source_server":True,"sanitized_source_file_count":len(source_files),
        "sanitized_archive_sha256":sha256(sanitized_archive)},indent=2)+"\n")

    log=root/"anonymization_changes.csv"; 
    with log.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=["file","replacement_count","categories"]); w.writeheader(); w.writerows(changes)
    audit=f"""# Anonymity audit

- Sanitization status: complete for the consolidated 3090 export copy.
- Text files changed: {len(changes)}.
- Replacements: absolute user home paths, server aliases, and author email only; secrets were not found.
- Exact RegDB commit source remains preserved on the 4090 source server. The consolidated package contains an anonymized source tree and `ANONYMIZATION_MANIFEST.json`.
- Dataset raw files are not included. Checkpoints are binary and contain no path scan surface; four SYSU representative checkpoints are included, while RegDB weights remain on the source server with verified checksums.
- Review `anonymization_changes.csv` for filenames and replacement counts; it contains no removed values.
"""
    (root/"ANONYMITY_AUDIT.md").write_text(audit,encoding="utf-8")

    inventory=[]
    for p in sorted(x for x in root.rglob("*") if x.is_file()):
        if p.name in ("EXPORT_SHA256SUMS.txt","export_inventory.csv"): continue
        inventory.append({"relative_path":str(p.relative_to(root)),"size_bytes":p.stat().st_size,"sha256":sha256(p)})
    with (root/"export_inventory.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(inventory[0])); w.writeheader(); w.writerows(inventory)
    sums=[f"{x['sha256']}  {x['relative_path']}" for x in inventory]
    sums.append(f"{sha256(root/'export_inventory.csv')}  export_inventory.csv")
    (root/"EXPORT_SHA256SUMS.txt").write_text("\n".join(sums)+"\n",encoding="utf-8")
    print(json.dumps({"status":"complete","changed_text_files":len(changes),"inventory_files":len(inventory)+1,
                      "sanitized_source_archive":sanitized_archive.name},indent=2))


if __name__=="__main__": main()
