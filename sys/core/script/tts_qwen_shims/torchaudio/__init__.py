# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A stand-in: qwen_tts imports torchaudio only for its 25 Hz tokenizer, which Aurora does not use (no torchaudio build
exists for this torch)."""
