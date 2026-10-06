#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
#
# Aurora's own voice (mdl_tts): Piper in an environment of its own (it is GPL-3: a separate program, never imported
# into Aurora's code), and the voices of config/models.json "tts" (Italian paola, English ljspeech, ~130 MB).
#
#   bash sys/core/script/sys_tts_install.sh
set -euo pipefail
cd "$(dirname "$0")/../../.."
[ -x sys/runtime/piper/bin/piper ] || { python3 -m venv sys/runtime/piper && sys/runtime/piper/bin/pip install -q "piper-tts==1.8.0"; }
.venv/bin/python sys/core/script/sys_models_fetch.py --models tts --yes
echo "Prova." | sys/runtime/piper/bin/piper -m sys/models/tts/piper-voices/it/it_IT/paola/medium/it_IT-paola-medium.onnx -f /dev/null \
  && echo "✅ voice ready: restart aurora-api (or wait for the next restart)"
