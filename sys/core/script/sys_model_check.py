# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Can this machine run that local model, and how will Aurora speak to it? (owner, 9 Oct: «se uno lo vuole cambiare con
un modello suo magari più potente perché ha hardware»). Reads the GGUF's header only; nothing is changed.

    .venv/bin/python sys/core/script/sys_model_check.py path/to/model.gguf [--json]

Says: the architecture, mixture of experts or dense, the context, the size; the profile (mdl_formats: Aurora's own
ChatML for Qwen, the model's template for the others, how its reasoning is switched, its tool calls); and whether it
fits — whole in the GPUs' memory, with some experts in RAM (MoE only: what AURORA_LLM_CPU_MOE_LAYERS does), or not.
The room left for the context and for the encoder and re-ranker beside it is not measured here: the first run is.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from aurora import mdl_formats, mdl_gguf  # noqa: E402

ROOM_GB = 2.0      # left on the GPUs besides the weights: the context's cache and the compute buffers (an assumption)


def fit(meta: dict, vram_gb: float, ram_gb: float) -> dict:
    """whole / experts_in_ram / no, with the numbers it was decided on."""
    size, moe = float(meta["size_gb"]), int(meta.get("experts") or 0) > 0
    if vram_gb and size + ROOM_GB <= vram_gb:
        return {"verdict": "whole", "why": f"{size} GB of weights + {ROOM_GB} GB of room ≤ {vram_gb} GB of GPU memory"}
    if moe and vram_gb and size <= vram_gb + ram_gb * 0.5:
        return {"verdict": "experts_in_ram", "why": f"{size} GB > {vram_gb} GB of GPU memory: some experts in RAM "
                f"({ram_gb} GB), slower answers (M23 measured the transfer)"}
    return {"verdict": "no", "why": f"{size} GB of weights; GPU {vram_gb} GB, RAM {ram_gb} GB"
            + ("" if moe else " (a dense model cannot keep part of itself in RAM here)")}


def check(path: Path) -> dict:
    import sys_profile
    meta = mdl_gguf.meta(path)
    prof = mdl_formats.from_gguf(meta)
    vram = round(sum(g["vram_gb"] for g in sys_profile.gpus()), 1)
    return {"model": meta["name"], "architecture": meta["architecture"],
            "moe": f"{meta['experts_used']} of {meta['experts']} experts" if meta["experts"] else "dense",
            "context": meta["context"], "size_gb": meta["size_gb"], "profile": mdl_formats.describe(prof),
            "fit": fit(meta, vram, sys_profile.ram_gb())}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("gguf", type=Path)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try:
        out = check(a.gguf)
    except (OSError, mdl_gguf.NotGGUF) as e:
        print(f"not readable: {e}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(out, ensure_ascii=False))
        return 0
    p = out["profile"]
    print(f"{out['model']} ({out['architecture']}, {out['moe']}, context {out['context']}, {out['size_gb']} GB)")
    print(f"  format: {p['family']}, prompt {p['template']}, tool calls {p['tools']}, reasoning "
          f"{'the <think> block of Aurora’s prompt' if p['template'] == 'chatml' else p['think_on'] or p['system_on'] or 'not switched'}")
    print(f"  fits: {out['fit']['verdict']} — {out['fit']['why']}")
    return 0 if out["fit"]["verdict"] != "no" else 1


if __name__ == "__main__":
    sys.exit(main())
