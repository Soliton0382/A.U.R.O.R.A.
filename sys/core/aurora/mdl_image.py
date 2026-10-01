# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora paints: one image per request, on a GPU shared with the reasoner.

SDXL-Lightning needs ~6.2 GB (M27). When AURORA_IMAGE_GPU has less free memory and
AURORA_IMAGE_SWAP_LLM is on, the reasoner (aurora-llm) is stopped, the image is painted by a
separate process (img_paint.py, which exits and gives all its memory back), and the reasoner is
started again, whatever happened. The image gets the AI disclosure (sys_disclosure.mark_image)
and is saved in AURORA_IMAGE_DIR. One GPU job at a time: the swap is the only way both fit.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

from . import sys_config, sys_disclosure, sys_log

SCRIPT = Path(__file__).resolve().parents[1] / "script" / "img_paint.py"
LLM_UNIT = "aurora-llm"


def free_gb(gpu: int) -> float:
    out = subprocess.run(["nvidia-smi", "-i", str(gpu), "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True, check=True, timeout=30).stdout
    return float(out.strip()) / 1024


def _unit(verb: str, unit: str) -> None:
    subprocess.run(["systemctl", verb, unit], check=True, timeout=120)       # polkit rule 50-aurora.rules


def _active(unit: str) -> bool:
    return subprocess.run(["systemctl", "is-active", "--quiet", unit], timeout=30).returncode == 0


def _wait(cond, limit_s: float, step: float = 2.0) -> bool:
    end = time.time() + limit_s
    while time.time() < end:
        if cond():
            return True
        time.sleep(step)
    return cond()


def paint(prompt: str, name: str, cfg: sys_config.Config | None = None, emit=None, title: str = "") -> dict:
    """Paint `prompt` into AURORA_IMAGE_DIR/<name>.png. Returns {"file", "seconds", "swap", ...}."""
    cfg = cfg or sys_config.get()
    log = sys_log.get_logger("image")
    ev = emit or (lambda e, d: None)
    gpu, need = cfg["AURORA_IMAGE_GPU"], cfg["AURORA_IMAGE_MIN_FREE_GB"]
    out_dir = cfg.path("AURORA_IMAGE_DIR")
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    swapped = False
    free = free_gb(gpu)
    try:
        if free < need:
            if not (cfg["AURORA_IMAGE_SWAP_LLM"] and _active(LLM_UNIT)):
                raise RuntimeError(f"GPU {gpu}: {free:.1f} GB free, {need} GB needed, and the reasoner may not be swapped")
            log.info("planned swap: stopping %s to paint on GPU %d (%.1f GB free, %.1f needed)", LLM_UNIT, gpu, free, need)
            ev("image.swap", {"stop": LLM_UNIT})
            _unit("stop", LLM_UNIT)
            swapped = True
            if not _wait(lambda: free_gb(gpu) >= need, 90):
                raise RuntimeError(f"GPU {gpu} still has {free_gb(gpu):.1f} GB free after stopping {LLM_UNIT}")
        with tempfile.TemporaryDirectory() as tmp:
            pf, raw = Path(tmp) / "prompt.txt", Path(tmp) / "raw.png"
            pf.write_text(prompt, encoding="utf-8")
            r = subprocess.run([sys.executable, str(SCRIPT), "--prompt-file", str(pf), "--out", str(raw), "--gpu", str(gpu),
                                "--size", cfg["AURORA_IMAGE_SIZE"]], capture_output=True, text=True,
                               timeout=cfg["AURORA_IMAGE_TIMEOUT_S"])
            if r.returncode != 0 or not raw.exists():
                raise RuntimeError(f"img_paint failed ({r.returncode}): {r.stderr.strip()[-600:]}")
            stats = json.loads(r.stdout.strip().splitlines()[-1])
            from PIL import Image
            with Image.open(raw) as img:
                data = sys_disclosure.mark_image(img, title, "it", cfg)
        target = out_dir / f"{name}.png"
        target.write_bytes(data)
    finally:
        if swapped:
            _unit("start", LLM_UNIT)
            up = _wait(lambda: _llm_ok(cfg), cfg["AURORA_IMAGE_TIMEOUT_S"], 3)
            log.info("planned swap: %s started again (%s)", LLM_UNIT, "healthy" if up else "NOT healthy yet")
            ev("image.swap", {"start": LLM_UNIT, "healthy": up})
    result = {"file": target.name, "seconds": round(time.time() - t0, 1), "swap": swapped, **stats}
    log.info("painted %s: %s", target.name, result)
    ev("image.painted", result)
    return result


def _llm_ok(cfg: sys_config.Config) -> bool:
    try:
        return httpx.get(f"http://127.0.0.1:{cfg['AURORA_LLM_PORT']}/health", timeout=5).status_code == 200
    except httpx.HTTPError:
        return False
