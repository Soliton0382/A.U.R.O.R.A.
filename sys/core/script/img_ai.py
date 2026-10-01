# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""One picture job with an image model, then exit (all its GPU memory is given back). Run by mdl_image.gpu_job:

    python sys/core/script/img_ai.py --task edit    --in a.png --out b.png --gpu 1 --prompt-file p.txt
    python sys/core/script/img_ai.py --task upscale --in a.png --out b.png --gpu 1 --scale 4
    python sys/core/script/img_ai.py --task cutout  --in a.png --out b.png --gpu 1

 edit     FLUX.2 klein 4B (AURORA_EDIT_MODEL_DIR): the picture changed as the English prompt says; the long side kept
          at most 1024 px, both sides multiples of 16; model CPU offload (peak ~8 GB, M27)
 upscale  Swin2SR x4 real-world (AURORA_UPSCALE_MODEL_DIR), in tiles so that a large picture fits; x2 = x4 then halved
 cutout   SAM 2.1 (AURORA_SEGMENT_MODEL_DIR): the subject around the centre kept, the rest transparent (PNG with alpha)
The last line printed is JSON with the measures. The caller adds the AI disclosure.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aurora import sys_config  # noqa: E402


def edit(cfg, src, prompt: str, device: str, gpu: int) -> tuple:
    import torch
    from diffusers import Flux2KleinPipeline
    pipe = Flux2KleinPipeline.from_pretrained(str(cfg.path("AURORA_EDIT_MODEL_DIR")), torch_dtype=torch.bfloat16)
    pipe.enable_model_cpu_offload(gpu_id=gpu)
    w, h = src.size
    k = min(1.0, 1024 / max(w, h))
    w, h = max(256, int(w * k) // 16 * 16), max(256, int(h * k) // 16 * 16)
    img = src.convert("RGB").resize((w, h))
    out = pipe(image=img, prompt=prompt, height=h, width=w, num_inference_steps=4, guidance_scale=1.0,
               generator=torch.Generator("cpu").manual_seed(0)).images[0]
    return out, {"width": w, "height": h}


def upscale(cfg, src, scale: int, device: str) -> tuple:
    import numpy as np
    import torch
    from transformers import AutoImageProcessor, Swin2SRForImageSuperResolution
    d = str(cfg.path("AURORA_UPSCALE_MODEL_DIR"))
    proc = AutoImageProcessor.from_pretrained(d)
    model = Swin2SRForImageSuperResolution.from_pretrained(d).to(device).eval()
    alpha = src.getchannel("A") if "A" in src.getbands() else None    # a cut-out keeps its transparency
    img = src.convert("RGB")
    k = min(1.0, 1024 / max(img.size))                  # x4 of 1024 is 4096: enough for anything shown
    if k < 1:
        img = img.resize((int(img.width * k), int(img.height * k)))
    a = np.asarray(img)
    tile, pad = 256, 16
    out = np.zeros((a.shape[0] * 4, a.shape[1] * 4, 3), np.uint8)
    for y in range(0, a.shape[0], tile):
        for x in range(0, a.shape[1], tile):
            y0, x0 = max(0, y - pad), max(0, x - pad)
            y1, x1 = min(a.shape[0], y + tile + pad), min(a.shape[1], x + tile + pad)
            inp = proc(a[y0:y1, x0:x1], return_tensors="pt").pixel_values.to(device)
            with torch.no_grad():
                r = model(pixel_values=inp).reconstruction[0].clamp(0, 1).permute(1, 2, 0).cpu().numpy()
            r = (r * 255).round().astype(np.uint8)[: (y1 - y0) * 4, : (x1 - x0) * 4]
            cy, cx = (y - y0) * 4, (x - x0) * 4
            hh, ww = min(tile, a.shape[0] - y) * 4, min(tile, a.shape[1] - x) * 4
            out[y * 4: y * 4 + hh, x * 4: x * 4 + ww] = r[cy: cy + hh, cx: cx + ww]
    from PIL import Image
    res = Image.fromarray(out)
    if scale == 2:
        res = res.resize((res.width // 2, res.height // 2), Image.LANCZOS)
    if alpha is not None:                                # the model sees colours only: the alpha is enlarged apart
        res = res.convert("RGBA")
        res.putalpha(alpha.resize(res.size, Image.LANCZOS))
    return res, {"width": res.width, "height": res.height}


def cutout(cfg, src, device: str) -> tuple:
    import numpy as np
    import torch
    from PIL import Image
    from transformers import Sam2Model, Sam2Processor
    d = str(cfg.path("AURORA_SEGMENT_MODEL_DIR"))
    proc, model = Sam2Processor.from_pretrained(d), Sam2Model.from_pretrained(d).to(device).eval()
    img = src.convert("RGB")
    w, h = img.size
    box = [[[0, 0, w - 1, h - 1]]]                             # the whole frame (a subject may touch the border), the centre point
    pts = [[[[w / 2, h / 2]]]]
    inputs = proc(images=img, input_boxes=box, input_points=pts, input_labels=[[[1]]], return_tensors="pt").to(device)
    with torch.no_grad():
        out = model(**inputs, multimask_output=True)
    masks = proc.post_process_masks(out.pred_masks.cpu(), inputs["original_sizes"])[0][0]   # (n, h, w)
    best = int(out.iou_scores[0, 0].argmax())
    from PIL import ImageFilter
    m = Image.fromarray(masks[best].numpy().astype(np.uint8) * 255)
    m = m.filter(ImageFilter.MedianFilter(7)).filter(ImageFilter.GaussianBlur(1.2))   # no jagged rows, a soft edge
    rgba = img.convert("RGBA")
    rgba.putalpha(m)
    m = np.asarray(m)
    return rgba, {"width": w, "height": h, "kept_pct": round(100 * float((m > 0).mean()), 1),
                  "score": round(float(out.iou_scores[0, 0, best]), 3)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--task", choices=("edit", "upscale", "cutout"), required=True)
    ap.add_argument("--in", dest="inp", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--gpu", type=int, default=-1, help="-1: CPU")
    ap.add_argument("--prompt-file", type=Path)
    ap.add_argument("--scale", type=int, default=4, choices=(2, 4))
    a = ap.parse_args()
    from PIL import Image
    cfg = sys_config.get()
    device = f"cuda:{a.gpu}" if a.gpu >= 0 else "cpu"
    t0 = time.time()
    src = Image.open(a.inp)
    if a.task == "edit":
        res, info = edit(cfg, src, a.prompt_file.read_text(encoding="utf-8"), device, a.gpu)
    elif a.task == "upscale":
        res, info = upscale(cfg, src, a.scale, device)
    else:
        res, info = cutout(cfg, src, device)
    res.save(a.out, "PNG")
    peak = 0.0
    try:
        import torch
        if a.gpu >= 0:
            peak = torch.cuda.max_memory_allocated(a.gpu) / 2**30
    except Exception:  # noqa: BLE001
        pass
    print(json.dumps({"task": a.task, "seconds": round(time.time() - t0, 1), "peak_vram_gb": round(peak, 2), **info}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
