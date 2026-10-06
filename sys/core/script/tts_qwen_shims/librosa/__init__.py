# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A tiny stand-in for the three librosa calls qwen_tts makes (librosa needs numba/llvmlite, not installable here)."""
import numpy as np
import soundfile
import soxr

from . import filters  # noqa: F401


def load(path, sr=None, mono=True):
    y, rate = soundfile.read(path, dtype="float32", always_2d=True)
    y = y.mean(axis=1) if mono else y.T
    if sr and sr != rate:
        y, rate = resample(y, orig_sr=rate, target_sr=sr), sr
    return y, rate


def resample(y, orig_sr, target_sr, **_):
    return soxr.resample(np.asarray(y, dtype=np.float32), orig_sr, target_sr).astype(np.float32)
