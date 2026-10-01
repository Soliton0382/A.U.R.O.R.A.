# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Image generation benchmark: which model Aurora uses to paint (dreams, requests).

For each model: load time, time per image and peak VRAM at 1:1 and 16:9 sizes of at
least 1024 px, on the same prompts and seed; the images are saved for a visual check.
Results: <AURORA_STATUS_DIR>/bench/image/<timestamp>/{results.json, <model>_<size>_<n>.png}.

The GPU must be free (one GPU job at a time): stop aurora-llm first, or pick a GPU with
enough free memory. The script refuses to start when less than --min-free-gb is free.

    python sys/core/script/bench_image.py --gpu 0
    python sys/core/script/bench_image.py --gpu 0 --models klein sdxl-lightning
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aurora import sys_config  # noqa: E402

PROMPTS = [
    "portrait of a woman with white hair and a jewelled crown made of light, biomechanical, hyper-realistic, luminous",
    "a library floating in deep space, books turning into galaxies, fireflies, cinematic light",
    "a solitary soliton wave travelling through a topological landscape, scientific illustration, glowing",
]
SIZES = [(1024, 1024), (1280, 1280), (1344, 768), (1536, 864)]
MODELS = {
    "klein": ("image/FLUX.2-klein-4B", "Flux2KleinPipeline", 4, 1.0),
    "z-image": ("image/Z-Image-Turbo", "ZImagePipeline", 9, 0.0),
    "sdxl-lightning": (None, "StableDiffusionXLPipeline", 4, 0.0),
}


def free_gb(gpu: int) -> float:
    out = subprocess.run(["nvidia-smi", "-i", str(gpu), "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True, check=True).stdout
    return int(out.strip()) / 1024


def load(name: str, models_dir: Path, sdxl_dir: Path | None, device: str, offload: bool):
    import diffusers
    import torch
    path, cls, steps, guidance = MODELS[name]
    if name == "sdxl-lightning":
        if not sdxl_dir:
            raise SystemExit("--sdxl-dir is required for sdxl-lightning (folder with stable-diffusion-xl-base-1.0 and SDXL-Lightning)")
        pipe = diffusers.StableDiffusionXLPipeline.from_pretrained(sdxl_dir / "stable-diffusion-xl-base-1.0",
                                                                   torch_dtype=torch.float16, variant=None)
        pipe.load_lora_weights(str(sdxl_dir / "SDXL-Lightning" / "sdxl_lightning_4step_lora.safetensors"))
        pipe.fuse_lora()
        pipe.scheduler = diffusers.EulerDiscreteScheduler.from_config(pipe.scheduler.config, timestep_spacing="trailing")
    else:
        pipe = getattr(diffusers, cls).from_pretrained(models_dir / path, torch_dtype=torch.bfloat16)
    if offload:                                     # only the working component on the GPU (text encoder, then denoiser, then VAE)
        pipe.enable_model_cpu_offload(gpu_id=int(device.split(":")[1]))
        return pipe, steps, guidance
    return pipe.to(device), steps, guidance


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--gpu", type=int, required=True)
    ap.add_argument("--models", nargs="+", default=list(MODELS), choices=list(MODELS))
    ap.add_argument("--sdxl-dir", type=Path, help="previous installation's stablediffusion folder (read only)")
    ap.add_argument("--min-free-gb", type=float, default=14.0)
    ap.add_argument("--offload", action="store_true", help="model CPU offload: components move to the GPU in turn")
    ap.add_argument("--repeats", type=int, default=2, help="images per prompt and size (the first includes warm-up)")
    args = ap.parse_args()
    cfg = sys_config.get()
    free = free_gb(args.gpu)
    if free < args.min_free_gb:
        print(f"GPU {args.gpu}: {free:.1f} GB free, {args.min_free_gb} needed. Stop aurora-llm or choose another GPU.")
        return 2
    import torch
    device = f"cuda:{args.gpu}"
    out = cfg.path("AURORA_STATUS_DIR") / "bench" / "image" / time.strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    results = {"offload": args.offload, "gpu": args.gpu, "gpu_name": torch.cuda.get_device_name(args.gpu), "free_gb_before": round(free, 1), "models": {}}
    for name in args.models:
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats(args.gpu)
        t0 = time.time()
        pipe, steps, guidance = load(name, cfg.path("AURORA_MODELS_DIR"), args.sdxl_dir, device, args.offload)
        torch.cuda.synchronize(args.gpu)
        r = {"load_s": round(time.time() - t0, 1), "steps": steps, "runs": []}
        for w, h in SIZES:
            for pi, prompt in enumerate(PROMPTS):
                for rep in range(args.repeats):
                    torch.cuda.synchronize(args.gpu)
                    t = time.time()
                    img = pipe(prompt=prompt, width=w, height=h, num_inference_steps=steps, guidance_scale=guidance,
                               generator=torch.Generator(device).manual_seed(1234 + pi)).images[0]
                    torch.cuda.synchronize(args.gpu)
                    secs = time.time() - t
                    if rep == args.repeats - 1:
                        img.save(out / f"{name}_{w}x{h}_{pi}.png")
                    r["runs"].append({"size": f"{w}x{h}", "prompt": pi, "rep": rep, "seconds": round(secs, 2)})
                    print(f"{name} {w}x{h} p{pi} r{rep}: {secs:.2f} s", flush=True)
        r["peak_vram_gb"] = round(torch.cuda.max_memory_allocated(args.gpu) / 2**30, 2)
        warm = [x["seconds"] for x in r["runs"] if x["rep"] > 0]
        r["median_warm_s"] = sorted(warm)[len(warm) // 2] if warm else None
        results["models"][name] = r
        del pipe
        torch.cuda.empty_cache()
        (out / "results.json").write_text(json.dumps(results, indent=1))
        print(f"== {name}: load {r['load_s']} s, peak {r['peak_vram_gb']} GB, median warm {r['median_warm_s']} s", flush=True)
    print(f"results: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
