# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import numpy as np
from transformers.audio_utils import mel_filter_bank


def mel(sr, n_fft, n_mels=128, fmin=0.0, fmax=None, htk=False, norm="slaney", **_):
    """librosa.filters.mel: (n_mels, 1 + n_fft // 2), Slaney scale and norm by default."""
    fb = mel_filter_bank(num_frequency_bins=1 + n_fft // 2, num_mel_filters=n_mels, min_frequency=fmin,
                         max_frequency=fmax if fmax is not None else sr / 2.0, sampling_rate=sr,
                         norm="slaney" if norm == "slaney" else None, mel_scale="htk" if htk else "slaney")
    return fb.T.astype(np.float32)
