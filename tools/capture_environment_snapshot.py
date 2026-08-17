#!/usr/bin/env python3
"""Capture a dependency/hardware snapshot without host, user, IP, or secrets."""

import argparse
import datetime as dt
import json
import platform
import re
import subprocess
from pathlib import Path


def run(cmd):
    p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--source-commit", required=True)
    ap.add_argument("--gpu-indices", default="0,1,2,3")
    args = ap.parse_args(); args.output.mkdir(parents=True, exist_ok=True)

    import torch
    try:
        import torchvision
        torchvision_version = torchvision.__version__
    except Exception as e:
        torchvision_version = f"import_error:{type(e).__name__}"

    gpus = []
    for text_index in args.gpu_indices.split(","):
        index = int(text_index)
        rc, out, err = run(["nvidia-smi", "-i", str(index),
                            "--query-gpu=name,memory.total,driver_version,uuid",
                            "--format=csv,noheader,nounits"])
        if rc == 0 and out:
            name, memory, driver, _uuid = [x.strip() for x in out.splitlines()[0].split(",", 3)]
            gpus.append({"index": index, "status": "available", "name": name,
                         "memory_total_mib": int(memory), "driver": driver})
        else:
            gpus.append({"index": index, "status": "device_handle_error",
                         "detail": "nvidia-smi query failed; hostname/PCI address removed"})

    cudnn = torch.backends.cudnn.version()
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_commit": args.source_commit,
        "host_user_ip_removed": True,
        "environment_variables_exported": False,
        "software": {
            "python": platform.python_version(),
            "torch": torch.__version__, "torchvision": torchvision_version,
            "torch_cuda": torch.version.cuda, "cudnn": cudnn,
        },
        "gpus": gpus,
    }
    (args.output / "environment.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")

    rc, freeze, err = run(["python", "-m", "pip", "freeze"])
    clean = []
    for line in freeze.splitlines():
        line = re.sub(r"\s+@\s+file://\S+", " @ <local-build-path-redacted>", line)
        if line.startswith("-e ") or line.startswith("--editable "):
            line = "editable-install=<source-redacted>"
        line = re.sub(r"(?i)(https?://)[^/@\s]+:[^/@\s]+@", r"\1<credentials-redacted>@", line)
        clean.append(line)
    (args.output / "pip_freeze_sanitized.txt").write_text("\n".join(clean) + "\n")
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
