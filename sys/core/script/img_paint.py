# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Paint one image with SDXL-Lightning (4 steps) and exit, so that all its GPU memory is given back.

Run by mdl_image.paint (the dreams of aurora-rem), never by hand during another GPU job:

    python sys/core/script/img_paint.py --prompt-file p.txt --out raw.png --gpu 0 --size 1344x768

Model CPU offload keeps only the working component on the GPU: peak 6.21 GB, 2.8-3.8 s per
image once loaded (M27). The caller adds the AI disclosure; this script only paints.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aurora import sys_config  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--prompt-file", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--gpu", type=int, required=True)
    ap.add_argument("--size", default="1344x768")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()
    cfg = sys_config.get()
    import diffusers
    import torch
    w, h = (int(x) for x in args.size.lower().split("x"))
    root = cfg.path("AURORA_IMAGE_MODEL_DIR")
    t0 = time.time()
    base = root / "stable-diffusion-xl-base-1.0"
    fp16 = any((base / "unet").glob("*.fp16.safetensors"))   # the installer fetches the official fp16 variant
    pipe = diffusers.StableDiffusionXLPipeline.from_pretrained(base, torch_dtype=torch.float16,
                                                               variant="fp16" if fp16 else None)
    pipe.load_lora_weights(str(root / "sdxl_lightning_4step_lora.safetensors"))
    pipe.fuse_lora()
    pipe.scheduler = diffusers.EulerDiscreteScheduler.from_config(pipe.scheduler.config, timestep_spacing="trailing")
    pipe.enable_model_cpu_offload(gpu_id=args.gpu)
    load_s = time.time() - t0
    seed = args.seed if args.seed is not None else random.randrange(2**31)
    t1 = time.time()
    img = pipe(prompt=args.prompt_file.read_text(encoding="utf-8").strip(), width=w, height=h,
               num_inference_steps=4, guidance_scale=0.0,
               generator=torch.Generator(f"cuda:{args.gpu}").manual_seed(seed)).images[0]
    img.save(args.out)
    print(json.dumps({"load_s": round(load_s, 1), "paint_s": round(time.time() - t1, 1), "seed": seed,
                      "size": f"{w}x{h}", "peak_vram_gb": round(torch.cuda.max_memory_allocated(args.gpu) / 2**30, 2)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
