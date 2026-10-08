# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The hardware profile of this machine: which .env values fit its GPUs and memory.

    python sys/core/script/sys_profile.py          # readable report
    python sys/core/script/sys_profile.py --json   # for the installer: {"profile", "measured", "env", "notes"}

Only the reference profile is measured (docs/COMPATIBILITY.md); the others are the best guess from the
measurements of the reference machine (model sizes, M23 for experts in RAM) and are marked so: their
first run is their measurement.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys


def gpus() -> list[dict]:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=index,name,memory.total,compute_cap", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=30, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    rows = []
    for line in out.strip().splitlines():
        i, name, mem, cap = (x.strip() for x in line.split(","))
        rows.append({"index": int(i), "name": name, "vram_gb": round(int(mem) / 1024, 1), "compute_cap": cap})
    return rows


def ram_gb() -> float:
    return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30, 1)


def cpu_bf16() -> bool:
    """The processor computes in bfloat16 natively (AVX-512 BF16 or AMX): 2.8x faster re-ranking than float32 (M151)."""
    try:
        flags = next((l for l in open("/proc/cpuinfo", encoding="utf-8") if l.startswith("flags")), "").split()
    except OSError:
        return False
    return "avx512_bf16" in flags or "amx_bf16" in flags


def cloud(ram: float, why: str) -> dict:
    """No local reasoner: the reasoning goes to a cloud provider (masked, with the owner's exemption); the encoder and
    the re-ranker stay here, on the CPU (the vault is never sent away to be indexed). Fewer candidates, shorter
    passages: 30 at 512 tokens re-ranked in 3.5 s (bfloat16) or 9.8 s (float32) on 4 cores of the reference CPU (M151)."""
    dtype = "bfloat16" if cpu_bf16() else "float32"
    notes = [why, f"re-ranking on the CPU in {dtype}, not measured on this CPU (M151: 30 passages in "
                  f"{'3.5' if dtype == 'bfloat16' else '9.8'} s on 4 cores of a Ryzen 7 7700X)"]
    if ram < 12:                                       # M151: models 5.0 GB at peak + API 2.0 + harvester 0.5
        notes.append(f"RAM {ram} GB: 12 GB or more advised (measured: the models' service 5.0 GB at its peak, "
                     "the API 2.0 GB, the harvester 0.5 GB)")
    return {"profile": "cloud: no local reasoner", "measured": False, "cloud": True, "env": {
        "AURORA_LLM_BACKEND": "cloud", "AURORA_EMBEDDER_DEVICE": "cpu", "AURORA_EMBEDDER_DTYPE": dtype,
        "AURORA_EMBEDDER_BATCH": "8", "AURORA_RERANKER_DEVICE": "cpu", "AURORA_RERANKER_DTYPE": dtype,
        "AURORA_RERANKER_BATCH": "8", "AURORA_RERANKER_MAX_TOKENS": "512", "AURORA_SEARCH_CANDIDATES": "30",
        "AURORA_IMAGE_ENABLED": "0"}, "notes": notes}


def choose(g: list[dict], ram: float) -> dict:
    big = [x for x in g if x["vram_gb"] >= 15]
    if len(big) >= 2:
        a, b = big[0]["index"], big[1]["index"]
        return {"profile": "reference: 2 GPUs of 16 GB or more", "measured": True, "env": {
            "AURORA_LLM_GPUS": f"{a},{b}", "AURORA_LLM_TENSOR_SPLIT": "4.5,3.5", "AURORA_LLM_CPU_MOE_LAYERS": "0",
            "AURORA_LLM_CTX": "32768", "AURORA_EMBEDDER_DEVICE": f"cuda:{b}", "AURORA_RERANKER_DEVICE": f"cuda:{b}",
            "AURORA_IMAGE_GPU": str(a)},
            "notes": ["measured: 112 tokens/s, retrieval M31, dreams M27"]}
    if big and big[0]["vram_gb"] >= 23:
        a = big[0]["index"]
        return {"profile": "one GPU of 24 GB or more", "measured": False, "env": {
            "AURORA_LLM_GPUS": str(a), "AURORA_LLM_TENSOR_SPLIT": "1", "AURORA_LLM_CPU_MOE_LAYERS": "8",
            "AURORA_LLM_CTX": "32768", "AURORA_EMBEDDER_DEVICE": f"cuda:{a}", "AURORA_RERANKER_DEVICE": f"cuda:{a}",
            "AURORA_IMAGE_GPU": str(a)},
            "notes": ["not measured: some MoE experts in RAM to leave room for encoder and re-ranker"]}
    if big:
        a = big[0]["index"]
        notes = ["not measured: most MoE experts in RAM (M23 measured the transfer cost), slower answers"]
        if ram < 48:
            notes.append(f"RAM {ram} GB: 48 GB or more advised for the experts kept in RAM")
        return {"profile": "one GPU of 16 GB", "measured": False, "env": {
            "AURORA_LLM_GPUS": str(a), "AURORA_LLM_TENSOR_SPLIT": "1", "AURORA_LLM_CPU_MOE_LAYERS": "28",
            "AURORA_LLM_CTX": "16384", "AURORA_EMBEDDER_DEVICE": f"cuda:{a}", "AURORA_RERANKER_DEVICE": f"cuda:{a}",
            "AURORA_IMAGE_GPU": str(a)}, "notes": notes}
    return cloud(ram, "no NVIDIA GPU with 16 GB or more: the reasoning goes to a cloud provider")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--cloud", action="store_true", help="the cloud profile even where a GPU could run the reasoner")
    args = ap.parse_args()
    g, ram = gpus(), ram_gb()
    p = {**(cloud(ram, "chosen: the reasoning goes to a cloud provider") if args.cloud else choose(g, ram)),
         "gpus": g, "ram_gb": ram}
    if args.json:
        print(json.dumps(p))
    else:
        for x in g:
            print(f"GPU {x['index']}: {x['name']}, {x['vram_gb']} GB, compute capability {x['compute_cap']}")
        print(f"RAM: {ram} GB\nprofile: {p['profile']} ({'measured' if p['measured'] else 'NOT measured'})")
        for k, v in p["env"].items():
            print(f"  {k}={v}")
        for n in p["notes"]:
            print(f"  note: {n}")
    return 0 if p["env"] else 1


if __name__ == "__main__":
    sys.exit(main())
