# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Whisper on a GPU only with room (M204): the CPU otherwise, and always when asked."""
import sys
from types import SimpleNamespace

from aurora import mdl_stt


def _torch(free_gb):
    cuda = SimpleNamespace(is_available=lambda: bool(free_gb), device_count=lambda: len(free_gb),
                           mem_get_info=lambda i: (free_gb[i] * 1e9, 16e9))
    return SimpleNamespace(cuda=cuda)


def test_the_gpu_with_room_else_the_cpu(cfg, monkeypatch):
    cfg.values["AURORA_STT_DEVICE"] = "auto"
    monkeypatch.setitem(sys.modules, "torch", _torch([1.8, 4.2]))
    assert mdl_stt.place(cfg) == "cuda:1"
    monkeypatch.setitem(sys.modules, "torch", _torch([1.8, 2.5]))
    assert mdl_stt.place(cfg) == "cpu"                       # no GPU with 3 GB: the embedder keeps its room
    monkeypatch.setitem(sys.modules, "torch", _torch([]))
    assert mdl_stt.place(cfg) == "cpu"
    cfg.values["AURORA_STT_DEVICE"] = "cpu"
    monkeypatch.setitem(sys.modules, "torch", _torch([9.0]))
    assert mdl_stt.place(cfg) == "cpu"
