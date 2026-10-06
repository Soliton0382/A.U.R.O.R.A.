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

import contextlib
import fcntl
import io
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


def gpu_busy(cfg: sys_config.Config) -> bool:
    """A GPU job holds the lock now (a picture, an edit, a video): asked without waiting."""
    f = cfg.path("AURORA_STATUS_DIR") / "gpu.lock"
    if not f.is_file():
        return False
    with open(f, "a+", encoding="utf-8") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(fh, fcntl.LOCK_UN)
        return False


def free_gb(gpu: int) -> float:
    out = subprocess.run(["nvidia-smi", "-i", str(gpu), "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True, check=True, timeout=30).stdout
    return float(out.strip()) / 1024


@contextlib.contextmanager
def gpu_lock(cfg: sys_config.Config, wait_s: float, what: str):
    """One GPU job at a time across processes (the API's edits and videos, the REM's dreams): a file lock in the
    status folder, waited for at most `wait_s` seconds. The holder writes what it is doing, for the error message."""
    f = cfg.path("AURORA_STATUS_DIR") / "gpu.lock"
    f.parent.mkdir(parents=True, exist_ok=True)
    with open(f, "a+", encoding="utf-8") as fh:
        end = time.time() + wait_s
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.time() >= end:
                    fh.seek(0)
                    raise RuntimeError(f"the GPU is busy with another job: {fh.read().strip() or 'unknown'}") from None
                time.sleep(2)
        fh.seek(0)
        fh.truncate()
        fh.write(f"{what} since {time.strftime('%H:%M:%S')}")
        fh.flush()
        from . import mdl_tts
        mdl_tts.release()                             # the natural voice gives its GPU memory back first
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


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
    cloud = _cloud(cfg, "image", prompt, None, log)           # the Models page may give new pictures to a provider
    if cloud is not None:
        from PIL import Image
        out_dir = cfg.path("AURORA_IMAGE_DIR")
        out_dir.mkdir(parents=True, exist_ok=True)
        with Image.open(io.BytesIO(cloud[0])) as img:
            data = sys_disclosure.mark_image(img.convert("RGB"), title, "it", cfg)
        target = out_dir / f"{name}.png"
        target.write_bytes(data)
        result = {"file": target.name, "swap": False, **cloud[1]}
        ev("image.painted", result)
        return result
    gpu, need = cfg["AURORA_IMAGE_GPU"], cfg["AURORA_IMAGE_MIN_FREE_GB"]
    out_dir = cfg.path("AURORA_IMAGE_DIR")
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    swapped = False
    lock = gpu_lock(cfg, cfg["AURORA_IMAGE_TIMEOUT_S"], f"dream {name}")
    lock.__enter__()
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
        lock.__exit__(None, None, None)
    result = {"file": target.name, "seconds": round(time.time() - t0, 1), "swap": swapped, **stats}
    log.info("painted %s: %s", target.name, result)
    ev("image.painted", result)
    return result



def paint_many(prompts: list[str], out_dir: Path, cfg: sys_config.Config | None = None, emit=None,
               size: str | None = None, title: str = "") -> dict:
    """Many pictures on this machine (never the cloud: no cost), the model loaded once and the reasoner swapped out
    once — a video's scenes. Files out_dir/scene-<n>.png, each with the AI disclosure. Returns {"files", "seconds", ...}."""
    cfg = cfg or sys_config.get()
    log = sys_log.get_logger("image")
    ev = emit or (lambda e, d: None)
    gpu, need, t0, swapped = cfg["AURORA_IMAGE_GPU"], cfg["AURORA_IMAGE_MIN_FREE_GB"], time.time(), False
    out_dir.mkdir(parents=True, exist_ok=True)
    timeout = cfg["AURORA_IMAGE_TIMEOUT_S"] * max(1, len(prompts))
    with gpu_lock(cfg, cfg["AURORA_IMAGE_TIMEOUT_S"], f"{len(prompts)} pictures"):
        try:
            if free_gb(gpu) < need:
                if not (cfg["AURORA_IMAGE_SWAP_LLM"] and _active(LLM_UNIT)):
                    raise RuntimeError(f"GPU {gpu}: {free_gb(gpu):.1f} GB free, {need} GB needed, and the reasoner may not be swapped")
                log.info("planned swap: stopping %s to paint %d pictures", LLM_UNIT, len(prompts))
                ev("image.swap", {"stop": LLM_UNIT})
                _unit("stop", LLM_UNIT)
                swapped = True
                if not _wait(lambda: free_gb(gpu) >= need, 90):
                    raise RuntimeError(f"GPU {gpu} still has {free_gb(gpu):.1f} GB free after stopping {LLM_UNIT}")
            with tempfile.TemporaryDirectory() as tmp:
                jobs = [{"prompt": p, "out": str(Path(tmp) / f"raw-{i}.png")} for i, p in enumerate(prompts, 1)]
                (Path(tmp) / "batch.json").write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
                ev("image.batch", {"pictures": len(jobs)})
                r = subprocess.run([sys.executable, str(SCRIPT), "--batch-file", str(Path(tmp) / "batch.json"), "--gpu", str(gpu),
                                    "--size", size or cfg["AURORA_IMAGE_SIZE"]], capture_output=True, text=True, timeout=timeout)
                if r.returncode != 0:
                    raise RuntimeError(f"img_paint failed ({r.returncode}): {r.stderr.strip()[-600:]}")
                stats = json.loads(r.stdout.strip().splitlines()[-1])
                from PIL import Image
                files = []
                for i, job in enumerate(jobs, 1):
                    with Image.open(job["out"]) as img:
                        target = out_dir / f"scene-{i}.png"
                        target.write_bytes(sys_disclosure.mark_image(img, title, "it", cfg))
                        files.append(target)
        finally:
            if swapped:
                _unit("start", LLM_UNIT)
                up = _wait(lambda: _llm_ok(cfg), cfg["AURORA_IMAGE_TIMEOUT_S"], 3)
                log.info("planned swap: %s started again (%s)", LLM_UNIT, "healthy" if up else "NOT healthy yet")
                ev("image.swap", {"start": LLM_UNIT, "healthy": up})
    result = {"files": files, "seconds": round(time.time() - t0, 1), "swap": swapped, **stats}
    log.info("painted %d pictures: %s", len(files), {k: v for k, v in result.items() if k != "files"})
    return result

AI_SCRIPT = Path(__file__).resolve().parents[1] / "script" / "img_ai.py"


def _cloud(cfg: sys_config.Config, task: str, prompt: str, src: bytes | None, log) -> tuple[bytes, dict] | None:
    """The picture from the provider the Models page chose for `task`, as PNG, or None: local, or the cloud failed
    or refused (a photo on an installation not exempted) — then the local model does it, and the trace says why."""
    from . import mdl_media
    if mdl_media.provider(cfg, task)[0] == "local":
        return None
    try:
        data, st = mdl_media.picture(cfg, task, prompt, src)
        from PIL import Image
        with Image.open(io.BytesIO(data)) as img:
            buf = io.BytesIO()
            img.save(buf, "PNG")
        return buf.getvalue(), st
    except Exception as e:                                # noqa: BLE001 — the local model is the fallback
        log.warning("cloud %s failed, local instead: %s", task, e)
        sys_log.trace("llm_client", "cloud.fallback", {"role": task, "provider": mdl_media.provider(cfg, task)[0],
                                                       "error": str(e)[:300]})
        return None


def gpu_job(task: str, src: bytes, cfg: sys_config.Config | None = None, emit=None, need_gb: float = 0.0,
            prompt: str = "", scale: int = 4) -> tuple[bytes, dict]:
    """A picture job of img_ai.py (edit, upscale, cutout) on AURORA_IMAGE_GPU, in its own process. When the GPU has
    less than `need_gb` free, the reasoner is stopped for the job and started again whatever happens (as for dreams).
    need_gb 0 runs on the CPU. Returns (PNG bytes, measures)."""
    cfg = cfg or sys_config.get()
    log = sys_log.get_logger("image")
    ev = emit or (lambda e, d: None)
    if task == "creative":                                   # a creative edit may go to a provider (Models page)
        cloud = _cloud(cfg, "edit", prompt, src, log)
        if cloud is not None:
            return cloud
    gpu, swapped, t0 = cfg["AURORA_IMAGE_GPU"], False, time.time()
    lock = gpu_lock(cfg, cfg["AURORA_IMAGE_TIMEOUT_S"], f"picture {task}")
    lock.__enter__()
    try:
        if need_gb and free_gb(gpu) < need_gb:
            if not (cfg["AURORA_IMAGE_SWAP_LLM"] and _active(LLM_UNIT)):
                raise RuntimeError(f"GPU {gpu}: {free_gb(gpu):.1f} GB free, {need_gb} GB needed, and the reasoner may not be swapped")
            log.info("planned swap for %s: stopping %s", task, LLM_UNIT)
            ev("image.swap", {"stop": LLM_UNIT, "task": task})
            _unit("stop", LLM_UNIT)
            swapped = True
            if not _wait(lambda: free_gb(gpu) >= need_gb, 90):
                raise RuntimeError(f"GPU {gpu} still has {free_gb(gpu):.1f} GB free after stopping {LLM_UNIT}")
        with tempfile.TemporaryDirectory() as tmp:
            inp, out, pf = Path(tmp) / "in.png", Path(tmp) / "out.png", Path(tmp) / "prompt.txt"
            inp.write_bytes(src)
            pf.write_text(prompt, encoding="utf-8")
            cmd = [sys.executable, str(AI_SCRIPT), "--task", task, "--in", str(inp), "--out", str(out),
                   "--gpu", str(gpu if need_gb else -1), "--prompt-file", str(pf), "--scale", str(scale)]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=cfg["AURORA_IMAGE_TIMEOUT_S"])
            if r.returncode != 0 or not out.exists():
                raise RuntimeError(f"img_ai {task} failed ({r.returncode}): {r.stderr.strip()[-600:]}")
            stats = json.loads(r.stdout.strip().splitlines()[-1])
            data = out.read_bytes()
    finally:
        if swapped:
            _unit("start", LLM_UNIT)
            up = _wait(lambda: _llm_ok(cfg), cfg["AURORA_IMAGE_TIMEOUT_S"], 3)
            log.info("planned swap: %s started again (%s)", LLM_UNIT, "healthy" if up else "NOT healthy yet")
            ev("image.swap", {"start": LLM_UNIT, "healthy": up})
        lock.__exit__(None, None, None)
    stats.update(total_seconds=round(time.time() - t0, 1), swap=swapped)
    log.info("%s done: %s", task, stats)
    return data, stats


def _llm_ok(cfg: sys_config.Config) -> bool:
    try:
        return httpx.get(f"http://127.0.0.1:{cfg['AURORA_LLM_PORT']}/health", timeout=5).status_code == 200
    except httpx.HTTPError:
        return False
