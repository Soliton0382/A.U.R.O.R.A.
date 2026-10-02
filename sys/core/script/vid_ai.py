# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""One short video with Wan 2.2 TI2V 5B, then exit (all its GPU memory is given back). Run by mdl_video.generate:

    python sys/core/script/vid_ai.py --prompt-file p.txt --out v.mp4 --gpu 0 [--image a.png] [--size 1280x704]
                                     [--frames 121] [--steps 50] [--label "AI · Aurora"] [--meta-file m.json]

 from words   WanPipeline: the English prompt becomes the video
 from a photo WanImageToVideoPipeline: the photo is the first frame, resized to the same area keeping its shape
The transformer in bf16, the VAE in fp32 with tiling, model CPU offload (one part at a time on the GPU). The frames get
the visible label (unless --label is empty) and are encoded with ffmpeg (H.264, 24 fps, yuv420p, faststart) with the
metadata of --meta-file. The last line printed is JSON with the measures.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aurora import sys_config  # noqa: E402

FPS = 24
NEGATIVE = ("blurry, low quality, distorted, deformed, watermark, text, subtitles, static frame, jpeg artifacts, "
            "extra fingers, bad anatomy, overexposed")


def fit(w: int, h: int, area: int, mod: int) -> tuple[int, int]:
    """The size with about `area` pixels and the shape w:h, both sides multiples of `mod`."""
    k = (area / (w * h)) ** 0.5
    return max(mod, round(w * k / mod) * mod), max(mod, round(h * k / mod) * mod)


def label_frames(frames, text: str):
    """The visible AI label on every frame (bottom right), as for pictures."""
    import numpy as np
    from PIL import Image, ImageDraw
    if not text:
        return frames
    out = []
    for f in frames:
        img = Image.fromarray(f)
        draw = ImageDraw.Draw(img, "RGBA")
        w, h = img.size
        size = max(12, w // 60)
        box = (w - size * 7 - 12, h - size - 14, w - 6, h - 6)
        draw.rounded_rectangle(box, radius=6, fill=(0, 0, 0, 140))
        draw.text((box[0] + 6, box[1] + 3), text, fill=(255, 255, 255, 230))
        out.append(np.asarray(img))
    return out


def encode(frames, out: Path, meta: dict) -> None:
    h, w = frames[0].shape[:2]
    cmd = ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(FPS),
           "-i", "-", "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    for k, v in meta.items():
        cmd += ["-metadata", f"{k}={v}"]
    p = subprocess.Popen([*cmd, str(out)], stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    for f in frames:
        p.stdin.write(f.tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError(f"ffmpeg failed: {p.stderr.read().decode()[-400:]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--prompt-file", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--gpu", type=int, required=True)
    ap.add_argument("--image", type=Path)
    ap.add_argument("--size", default="1280x704", help="WxH for a video from words; the area for one from a photo")
    ap.add_argument("--frames", type=int, default=121, help="4k+1; 121 = 5 s at 24 fps")
    ap.add_argument("--steps", type=int, default=50)
    ap.add_argument("--label", default="AI · Aurora")
    ap.add_argument("--meta-file", type=Path)
    ap.add_argument("--fp8", action="store_true", help="transformer weights stored in fp8, computed in bf16 (half the memory)")
    a = ap.parse_args()
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    import numpy as np
    import torch
    from diffusers import AutoencoderKLWan, WanImageToVideoPipeline, WanPipeline
    cfg = sys_config.get()
    d = str(cfg.path("AURORA_VIDEO_MODEL_DIR"))
    t0 = time.time()
    frames_n = max(5, (a.frames - 1) // 4 * 4 + 1)
    w, h = (int(x) for x in a.size.lower().split("x"))
    vae = AutoencoderKLWan.from_pretrained(d, subfolder="vae", torch_dtype=torch.float32)
    import diffusers.pipelines.wan.pipeline_wan_i2v as i2v
    if not hasattr(i2v, "ftfy"):                       # diffusers 0.40: the i2v prompt cleaning calls ftfy unguarded;
        from types import SimpleNamespace             # the t2v pipeline skips it when ftfy is missing: the same here
        i2v.ftfy = SimpleNamespace(fix_text=lambda text: text)
    kind = WanImageToVideoPipeline if a.image else WanPipeline
    pipe = kind.from_pretrained(d, vae=vae, torch_dtype=torch.bfloat16)
    if a.fp8:
        pipe.transformer.enable_layerwise_casting(storage_dtype=torch.float8_e4m3fn, compute_dtype=torch.bfloat16)
    pipe.enable_model_cpu_offload(gpu_id=a.gpu)
    if hasattr(pipe.vae, "enable_tiling"):
        pipe.vae.enable_tiling()
    args = dict(prompt=a.prompt_file.read_text(encoding="utf-8"), negative_prompt=NEGATIVE, num_frames=frames_n,
                num_inference_steps=a.steps, guidance_scale=5.0, generator=torch.Generator("cpu").manual_seed(0))
    mod = pipe.vae_scale_factor_spatial * pipe.transformer.config.patch_size[1]
    if a.image:
        from PIL import Image
        src = Image.open(a.image).convert("RGB")
        w, h = fit(src.width, src.height, w * h, mod)
        args["image"] = src.resize((w, h), Image.LANCZOS)
    else:
        w, h = w // mod * mod, h // mod * mod
    loaded = time.time() - t0
    out = pipe(height=h, width=w, output_type="np", **args).frames[0]           # (frames, h, w, 3) in 0..1
    made = time.time() - t0 - loaded
    frames = [(f * 255).round().clip(0, 255).astype(np.uint8) for f in out]
    meta = json.loads(a.meta_file.read_text(encoding="utf-8")) if a.meta_file else {}
    encode(label_frames(frames, a.label), a.out, meta)
    peak = torch.cuda.max_memory_allocated(a.gpu) / 2**30
    print(json.dumps({"from": "image" if a.image else "words", "width": w, "height": h, "frames": len(frames),
                      "seconds_video": round(len(frames) / FPS, 2), "steps": a.steps, "load_s": round(loaded, 1),
                      "generate_s": round(made, 1), "seconds": round(time.time() - t0, 1), "peak_vram_gb": round(peak, 2)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
