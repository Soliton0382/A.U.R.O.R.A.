# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's natural voice, kept loaded: Qwen3-TTS cloning the owner's reference clip (AURORA_TTS_QWEN_REF, chosen by
the owner on 2026-10-06, never published). Started by mdl_tts with sys/runtime/qwen-tts/pkgs on PYTHONPATH (its own transformers), one request per
line on stdin — {"text", "lang", "out"} — one JSON line back on stdout: {"ok", "seconds", "audio_s"} or {"ok": false,
"error"}. It exits when stdin closes (mdl_tts closes it after AURORA_TTS_QWEN_IDLE_S without requests, or before
a GPU job), giving all its GPU memory back.
    tts_qwen_worker.py --model DIR --ref FILE.flac --ref-text FILE.txt --device cuda:1
"""
from __future__ import annotations

import argparse
import json
import sys
import time

LANGS = {"it": "Italian", "en": "English", "de": "German", "fr": "French", "es": "Spanish", "pt": "Portuguese"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", required=True)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--ref-text", required=True)
    ap.add_argument("--device", default="cuda:1")
    a = ap.parse_args()
    out, sys.stdout = sys.stdout, sys.stderr          # the libraries print warnings: only the replies go to stdout
    import soundfile
    import torch
    from qwen_tts import Qwen3TTSModel
    t0 = time.time()
    model = Qwen3TTSModel.from_pretrained(a.model, device_map=a.device,
                                          dtype=torch.bfloat16 if a.device.startswith("cuda") else torch.float32)
    with open(a.ref_text, encoding="utf-8") as f:
        prompt = model.create_voice_clone_prompt(ref_audio=a.ref, ref_text=f.read().strip())
    print(json.dumps({"ok": True, "ready": True, "load_s": round(time.time() - t0, 1)}), file=out, flush=True)
    for line in sys.stdin:
        try:
            req = json.loads(line)
            t1 = time.time()
            wavs, sr = model.generate_voice_clone(text=req["text"], language=LANGS.get(str(req.get("lang", "it"))[:2], "Italian"),
                                                  voice_clone_prompt=prompt)
            soundfile.write(req["out"], wavs[0], sr)
            print(json.dumps({"ok": True, "seconds": round(time.time() - t1, 1), "audio_s": round(len(wavs[0]) / sr, 1)}),
                  file=out, flush=True)
        except Exception as e:  # noqa: BLE001 — one bad request is told, the voice stays loaded
            print(json.dumps({"ok": False, "error": str(e)[:300]}), file=out, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
