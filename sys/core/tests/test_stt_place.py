# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Whisper on a GPU only with room (M204): the CPU otherwise, and always when asked. The room is nvidia-smi's, so no
CUDA context is opened on the GPUs Whisper does not take (C413)."""
import os
import sys
from types import SimpleNamespace

import pytest

from aurora import mdl_stt

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="a shell stand-in for nvidia-smi")


def _gpus(tmp_path, monkeypatch, free_gb):
    """torch that sees the GPUs and an nvidia-smi that prints their free MiB; torch is never asked for memory."""
    cuda = SimpleNamespace(is_available=lambda: bool(free_gb))
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=cuda))
    rows = "".join(f"{i}, {int(g * 1e9 / 2**20)}\\n" for i, g in enumerate(free_gb))
    smi = tmp_path / "nvidia-smi"
    smi.write_text(f"#!/bin/sh\nprintf '{rows}'\n")
    smi.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")


def test_the_gpu_with_room_else_the_cpu(cfg, tmp_path, monkeypatch):
    cfg.values["AURORA_STT_DEVICE"] = "auto"
    _gpus(tmp_path, monkeypatch, [1.8, 4.2])
    assert mdl_stt.place(cfg) == "cuda:1"
    _gpus(tmp_path, monkeypatch, [1.8, 2.5])
    assert mdl_stt.place(cfg) == "cpu"                       # no GPU with 3 GB: the embedder keeps its room
    _gpus(tmp_path, monkeypatch, [])
    assert mdl_stt.place(cfg) == "cpu"
    cfg.values["AURORA_STT_DEVICE"] = "cpu"
    _gpus(tmp_path, monkeypatch, [9.0])
    assert mdl_stt.place(cfg) == "cpu"


def test_no_nvidia_smi_answer_is_the_cpu(cfg, tmp_path, monkeypatch):
    cfg.values["AURORA_STT_DEVICE"] = "auto"
    _gpus(tmp_path, monkeypatch, [9.0])
    (tmp_path / "nvidia-smi").write_text("#!/bin/sh\nexit 9\n")
    assert mdl_stt.free_bytes() == [] and mdl_stt.place(cfg) == "cpu"
