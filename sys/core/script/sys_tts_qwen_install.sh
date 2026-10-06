#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
#
# Aurora's natural voice (mdl_tts, engine "qwen"): Qwen3-TTS 0.6B cloning a reference clip (AURORA_TTS_QWEN_REF, in
# the private state folder). The owner's own clip stays the owner's and is never published: an installation without one gets its
# own, said now by Piper (a different take each time); replace it with a clip of the voice you want (and its words).
# Its packages live apart, in sys/runtime/qwen-tts (qwen_tts pins transformers 4.57, Aurora uses 5.x): the torch of
# Aurora's environment is reused, librosa and torchaudio are replaced by two small stand-ins (script/tts_qwen_shims:
# librosa needs numba/llvmlite, torchaudio has no build for this torch). The model (~2.5 GB) from config/models.json.
#
#   bash sys/core/script/sys_tts_qwen_install.sh
set -euo pipefail
cd "$(dirname "$0")/../../.."
RT=sys/runtime/qwen-tts/pkgs
if [ ! -d "$RT/qwen_tts" ]; then
  mkdir -p "$RT"
  .venv/bin/python -m pip install -q --target "$RT" --no-deps \
    "qwen-tts==0.1.1" "transformers==4.57.3" "tokenizers==0.22.1" "huggingface_hub==0.36.2" "accelerate==1.12.0" \
    "einops==0.8.2" "soundfile==0.14.0" "soxr==1.1.0" "sox==1.5.0" "onnxruntime==1.30.0"
  cp -r sys/core/script/tts_qwen_shims/librosa sys/core/script/tts_qwen_shims/torchaudio "$RT/"
fi
.venv/bin/python sys/core/script/sys_models_fetch.py --models tts_qwen --yes
REF=$(.venv/bin/python -c "import sys; sys.path.insert(0, 'sys/core'); from aurora import sys_config; print(sys_config.get().path('AURORA_TTS_QWEN_REF'))")
if [ ! -f "$REF" ]; then
  mkdir -p "$(dirname "$REF")"
  WORDS="Ciao, sono Aurora. Sapevi che la luce nasce da un processo di emissione? Ogni scoperta comincia con una domanda, e la curiosità è il primo passo verso la conoscenza."
  echo "$WORDS" > "${REF%.flac}.txt"
  echo "$WORDS" | sys/runtime/piper/bin/piper -m sys/models/tts/piper-voices/it/it_IT/paola/medium/it_IT-paola-medium.onnx -f "${REF%.flac}.wav"
  ffmpeg -hide_banner -loglevel error -i "${REF%.flac}.wav" -c:a flac "$REF" && unlink "${REF%.flac}.wav"
  echo "✅ a reference voice of this installation's own: $REF"
fi
PYTHONPATH="$RT" .venv/bin/python -c "from qwen_tts import Qwen3TTSModel" \
  && echo "✅ Qwen3-TTS ready: the videos speak with it (AURORA_VIDEO_VOICE=qwen); the chat too with AURORA_TTS_ENGINE=qwen"
