#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's face animated for the start and the end of her narrated videos (owner, 2026-10-11: «il ciao e il saluto
fossero animati… intro e chiusura sono sempre le stesse, fatte una volta non serve rifarle»). Run once.

The portrait (webui/assets/aurora_face.png) cut to 9:16 around its centre becomes the first frame of two clips of
Wan 2.2 (mdl_video, from a picture): a hello and a goodbye. The model does not move lips to words, so she smiles and
waves rather than speaks — the voice goes over the clip in the montage (kno_story). The reasoner is stopped for each
clip and started again (one GPU, one job): about 18 minutes a clip (M57), about 35 in all.

    .venv/bin/python sys/core/script/story_intro_make.py            # both, the ones missing
    .venv/bin/python sys/core/script/story_intro_make.py --again    # both, made again
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aurora import kno_story, mdl_video, sys_config  # noqa: E402

PROMPTS = {
    "intro": ("The woman in the portrait looks into the camera, smiles warmly and raises her right hand to wave hello, "
              "a small natural nod of the head, she blinks softly, her hair moves slightly; mouth gently closed in a "
              "smile; soft even light, the background unchanged, static camera, photorealistic, calm and friendly."),
    "outro": ("The woman in the portrait smiles at the camera, gives a small nod and waves goodbye with her right hand, "
              "then lowers it and keeps smiling; mouth gently closed in a smile; she blinks softly, slight natural "
              "head movement; soft even light, the background unchanged, static camera, photorealistic, warm."),
}


def portrait() -> bytes:
    """The face cut to 9:16 around its centre, 720x1280 (the videos are vertical)."""
    from PIL import Image
    im = Image.open(kno_story.FACE).convert("RGB")
    w, h = im.size
    cw = min(w, round(h * 9 / 16))
    ch = min(h, round(cw * 16 / 9))
    left, top = (w - cw) // 2, (h - ch) // 2
    out = io.BytesIO()
    im.crop((left, top, left + cw, top + ch)).resize((720, 1280), Image.LANCZOS).save(out, "PNG")
    return out.getvalue()


def main() -> int:
    cfg = sys_config.get()
    cfg.values["AURORA_AI_IMAGE_LABEL"] = False         # the montage labels the whole video once (kno_story)
    again = "--again" in sys.argv
    folder = kno_story.intro_dir(cfg)
    folder.mkdir(parents=True, exist_ok=True)
    image = portrait()
    for kind, prompt in PROMPTS.items():
        target = folder / f"{kind}.mp4"
        if target.exists() and not again:
            print(f"{kind}: already there ({target})")
            continue
        print(f"{kind}: animating (about 18 minutes, the reasoner stopped meanwhile)…", flush=True)
        data, stats = mdl_video.generate(prompt, cfg, image=image, title=f"Aurora {kind}")
        target.write_bytes(data)
        print(f"{kind}: {target} ({len(data) // 1024} KB, {stats.get('total_seconds')} s)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
