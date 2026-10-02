# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora makes short videos: from words, or from a picture that becomes the first frame (Wan 2.2 TI2V 5B).

The model needs a whole GPU: the reasoner (aurora-llm) is stopped for the job and started again whatever happens,
under the GPU lock shared with dreams and picture edits (one GPU, one job). The video is made by a separate process
(vid_ai.py, which exits and gives all its memory back), carries the AI disclosure (EU AI Act art. 50: visible label
and metadata with the IPTC digital source type) and is returned as MP4 bytes.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import mdl_image, sys_config, sys_disclosure, sys_log

SCRIPT = Path(__file__).resolve().parents[1] / "script" / "vid_ai.py"
# a cheap filter before asking the reasoner: a message without one of these words never makes a video
WORDS = re.compile(r"\b(video\w*|filmat\w*|clip|animazion\w*|anim[ai](la|lo|li|le)?|animate?|movie)\b", re.I)
SYS_VIDEO = ("Decide whether the owner's last message asks Aurora to CREATE a new video (generate, make, animate a "
             "photo). A question ABOUT a video, a request to watch, describe or summarise one, or to find one online "
             "is NOT a request to create. Reply ONLY with JSON: {\"make\": true|false, \"from_picture\": true|false, "
             "\"prompt\": \"...\", \"title\": \"...\"}. from_picture: the owner wants the picture of the conversation "
             "animated (animala, questa foto, fai muovere). prompt: in ENGLISH, 40-80 words, what is seen and how it "
             "moves (subject, action, setting, light, camera movement, style); for a picture, the motion to add and "
             "that the scene stays the same. title: 2-5 words in the owner's language. Examples: 'fammi un video di "
             "un gatto che gioca con la neve' make; 'anima questa foto' make, from_picture; 'cosa succede nel video?' "
             "not make; 'cercami un video di cucina' not make.")


def plan(llm, message: str, has_picture: bool) -> dict | None:
    """{"from_picture", "prompt", "title"} when the message asks for a new video, else None."""
    if not WORDS.search(message):
        return None
    raw = llm.complete(SYS_VIDEO, f"PICTURE IN THE CONVERSATION: {'yes' if has_picture else 'no'}\n"
                                  f"LAST MESSAGE: {message}", 300).answer
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except ValueError:
        return None
    prompt = " ".join(str(d.get("prompt", "")).split())[:1200]
    if d.get("make") is not True or len(prompt) < 10:
        return None
    return {"from_picture": bool(d.get("from_picture")) and has_picture, "prompt": prompt,
            "title": " ".join(str(d.get("title") or "video").split())[:60]}


# measured (M57): 5 s at 1280x704 on an RTX 5060 Ti, fp8 weights: ~216 s fixed (text encoder, decoding, offload),
# 28 s per step; the time is taken as proportional to frames x pixels (attention grows faster: an estimate)
FIXED_S, STEP_S, REF_WORK = 216.0, 28.0, 121 * 1280 * 704
SWAP_S = 60.0                                          # reasoner stopped and started again


def estimate_minutes(cfg: sys_config.Config) -> int:
    w, h = (int(x) for x in str(cfg["AURORA_VIDEO_SIZE"]).lower().split("x"))
    k = (int(cfg["AURORA_VIDEO_SECONDS"] * 24) + 1) * w * h / REF_WORK
    return max(1, round((SWAP_S + k * (FIXED_S + STEP_S * cfg["AURORA_VIDEO_STEPS"])) / 60))


def available(cfg: sys_config.Config) -> bool:
    d = cfg.path("AURORA_VIDEO_MODEL_DIR")
    return (d / "model_index.json").exists() and (d / "transformer").is_dir()


def generate(prompt_en: str, cfg: sys_config.Config | None = None, emit=None, image: bytes | None = None,
             title: str = "", lang: str = "it") -> tuple[bytes, dict]:
    """The MP4 of `prompt_en` (English, as the model was trained), from `image` when given. Returns (bytes, measures)."""
    cfg = cfg or sys_config.get()
    log = sys_log.get_logger("video")
    ev = emit or (lambda e, d: None)
    if not available(cfg):
        raise RuntimeError("the video model is not installed: sys_models_fetch.py --models video")
    gpu, need, swapped, t0 = cfg["AURORA_IMAGE_GPU"], cfg["AURORA_VIDEO_MIN_FREE_GB"], False, time.time()
    on = sys_disclosure._on(cfg)
    label = "AI · Aurora" if on and cfg["AURORA_AI_IMAGE_LABEL"] else ""
    meta = {"title": title[:120], "encoder_tool": "Aurora"}
    if on:
        meta.update(comment=sys_disclosure._line(cfg, lang), description=sys_disclosure.IPTC_AI)
    with mdl_image.gpu_lock(cfg, 60, f"video {title[:40]}"):
        try:
            if mdl_image.free_gb(gpu) < need:
                if not (cfg["AURORA_IMAGE_SWAP_LLM"] and mdl_image._active(mdl_image.LLM_UNIT)):
                    raise RuntimeError(f"GPU {gpu}: {mdl_image.free_gb(gpu):.1f} GB free, {need} GB needed, "
                                       "and the reasoner may not be swapped")
                log.info("planned swap for a video: stopping %s", mdl_image.LLM_UNIT)
                ev("image.swap", {"stop": mdl_image.LLM_UNIT, "task": "video"})
                mdl_image._unit("stop", mdl_image.LLM_UNIT)
                swapped = True
                if not mdl_image._wait(lambda: mdl_image.free_gb(gpu) >= need, 90):
                    raise RuntimeError(f"GPU {gpu} still has {mdl_image.free_gb(gpu):.1f} GB free after stopping the reasoner")
            with tempfile.TemporaryDirectory() as tmp:
                pf, mf, out = Path(tmp) / "prompt.txt", Path(tmp) / "meta.json", Path(tmp) / "out.mp4"
                pf.write_text(prompt_en, encoding="utf-8")
                mf.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
                cmd = [sys.executable, str(SCRIPT), "--prompt-file", str(pf), "--out", str(out), "--gpu", str(gpu),
                       "--size", cfg["AURORA_VIDEO_SIZE"], "--frames", str(int(cfg["AURORA_VIDEO_SECONDS"] * 24) + 1),
                       "--steps", str(cfg["AURORA_VIDEO_STEPS"]), "--label", label, "--meta-file", str(mf), "--fp8"]
                if image:
                    (Path(tmp) / "in.png").write_bytes(image)
                    cmd += ["--image", str(Path(tmp) / "in.png")]
                ev("video.start", {"from": "image" if image else "words", "size": cfg["AURORA_VIDEO_SIZE"],
                                   "seconds": cfg["AURORA_VIDEO_SECONDS"], "steps": cfg["AURORA_VIDEO_STEPS"]})
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=cfg["AURORA_VIDEO_TIMEOUT_S"])
                if r.returncode != 0 or not out.exists():
                    raise RuntimeError(f"vid_ai failed ({r.returncode}): {r.stderr.strip()[-600:]}")
                stats = json.loads(r.stdout.strip().splitlines()[-1])
                data = out.read_bytes()
        finally:
            if swapped:
                mdl_image._unit("start", mdl_image.LLM_UNIT)
                up = mdl_image._wait(lambda: mdl_image._llm_ok(cfg), cfg["AURORA_IMAGE_TIMEOUT_S"], 3)
                log.info("planned swap: %s started again (%s)", mdl_image.LLM_UNIT, "healthy" if up else "NOT healthy yet")
                ev("image.swap", {"start": mdl_image.LLM_UNIT, "healthy": up})
    stats.update(total_seconds=round(time.time() - t0, 1), swap=swapped, bytes=len(data))
    log.info("video done: %s", stats)
    return data, stats
