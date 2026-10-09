# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A local reasoner of one's own (roadmap 73): looked at, checked before downloading, switched to, undone."""
import json
from types import SimpleNamespace

import pytest

from aurora import mdl_custom as C
from aurora import sys_config
from test_model_formats import MISTRAL, gguf


def test_a_repository_lists_its_models_split_ones_as_one_and_its_projectors(monkeypatch):
    sib = lambda n, gb: SimpleNamespace(rfilename=n, size=int(gb * 2**30))                       # noqa: E731
    info = SimpleNamespace(sha="abc123def456", tags=["license:apache-2.0"], card_data=None, siblings=[
        sib("M-Q4_K_M.gguf", 13.3), sib("M-Q8_0-00001-of-00002.gguf", 12), sib("M-Q8_0-00002-of-00002.gguf", 12.9),
        sib("mmproj-F16.gguf", 0.8), sib("README.md", 0)])
    import huggingface_hub
    monkeypatch.setattr(huggingface_hub, "HfApi", lambda: SimpleNamespace(model_info=lambda *a, **k: info))
    out = C.inspect("x/M-GGUF")
    assert out["licence"] == "apache-2.0" and out["revision"] == "abc123def456"
    assert [(f["file"], f["size_gb"], len(f["parts"])) for f in out["files"]] == \
        [("M-Q4_K_M.gguf", 13.3, 1), ("M-Q8_0-00001-of-00002.gguf", 24.9, 2)]
    assert [p["file"] for p in out["projectors"]] == ["mmproj-F16.gguf"]


def test_the_header_is_read_from_the_first_megabytes_asking_for_more_when_short(tmp_path, monkeypatch):
    f = tmp_path / "m.gguf"
    gguf(f, {"general.architecture": "llama", "general.name": "Mistral-Small", "tokenizer.chat_template": MISTRAL})
    whole = f.read_bytes()
    asked = []

    def get(url, headers):
        asked.append(headers["Range"])
        cut = 40 if len(asked) == 1 else len(whole)                     # the first range too short
        return SimpleNamespace(status_code=206, content=whole[:cut])
    out = C.check("x/m", "rev", "m.gguf", 13.3, machine=(32.0, 64.0), get=get)
    assert len(asked) == 2 and out["profile"]["family"] == "mistral" and out["fit"]["verdict"] == "whole"


def test_a_model_that_answers_is_used_and_one_that_does_not_is_undone(cfg, monkeypatch):
    from aurora import mdl_llm, mdl_modes, sys_health
    for p in ("sys/models/llm/custom/x/new.gguf", "sys/models/llm/qwen/old.gguf"):
        (cfg.root / p).parent.mkdir(parents=True, exist_ok=True)
        (cfg.root / p).write_bytes(b"x")
    sys_config.write_env(cfg.env_file, {"AURORA_LLM_MODEL": "sys/models/llm/qwen/old.gguf"})
    cfg.values["AURORA_LLM_MODEL"] = "sys/models/llm/qwen/old.gguf"
    monkeypatch.setattr(sys_health, "gpu_job", lambda c: "")
    restarts = []
    monkeypatch.setattr(mdl_modes, "_service", lambda verb, run=None: restarts.append(verb) or (0, ""))
    answer = {"text": "Roma"}

    class LLM:
        def __init__(self, c):
            self.model = c["AURORA_LLM_MODEL"]

        def health(self):
            return True

        def complete(self, *a):
            return SimpleNamespace(answer=answer["text"])
    monkeypatch.setattr(mdl_llm, "LLM", LLM)
    out = C.switch(cfg, "sys/models/llm/custom/x/new.gguf", wait_s=1)
    assert out["answer"] == "Roma" and not out["vision"] and "Visione" in out["note"]
    assert sys_config.parse_env(cfg.env_file.read_text())["AURORA_LLM_MODEL"] == "sys/models/llm/custom/x/new.gguf"
    assert json.loads((cfg.path("AURORA_STATUS_DIR") / "llm_previous.json").read_text())["AURORA_LLM_MODEL"] == \
        "sys/models/llm/qwen/old.gguf"
    answer["text"] = ""                                                    # the next one answers nothing
    cfg.values["AURORA_LLM_MODEL"] = "sys/models/llm/custom/x/new.gguf"
    with pytest.raises(C.CustomError, match="nothing"):
        C.switch(cfg, "sys/models/llm/qwen/old.gguf", wait_s=1)
    assert sys_config.parse_env(cfg.env_file.read_text())["AURORA_LLM_MODEL"] == "sys/models/llm/custom/x/new.gguf"
    assert restarts == ["restart", "restart", "restart"]                  # used; tried; put back


def test_never_during_a_gpu_job(cfg, monkeypatch):
    from aurora import sys_health
    monkeypatch.setattr(sys_health, "gpu_job", lambda c: "a painting")
    with pytest.raises(C.CustomError, match="GPU"):
        C.switch(cfg, "sys/models/llm/custom/x/new.gguf")
