# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A machine without a local reasoner (AURORA_LLM_BACKEND=cloud): every step goes to the cloud default, masked; without
the owner's exemption nothing leaves; no aurora-llm unit; the encoder and re-ranker stay on this machine's CPU."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from aurora import mdl_router, sys_config, sys_features
from aurora.mdl_llm import Completion

from conftest import write_env


@pytest.fixture
def cloud_cfg(tmp_path: Path) -> sys_config.Config:
    return sys_config.load(write_env(tmp_path, AURORA_LLM_BACKEND="cloud", AURORA_CLOUD_PROVIDER="openai",
                                     AURORA_CLOUD_MODEL="m1", AURORA_OPENAI_API_KEY="sk-test"), check_root=False)


class Provider:
    """A cloud provider that remembers what reached it."""
    seen: list = []

    def __init__(self, provider, model, cfg):
        self.name, self.model = provider, model

    def complete(self, system, user, max_tokens, think=False):
        Provider.seen.append(system + "\n" + user)
        return Completion("scrivi a [EMAIL_1]", "", 3, 0.1, False)


def test_the_steps_assigned_local_go_masked_to_the_cloud_default(cloud_cfg, monkeypatch):
    monkeypatch.setattr(mdl_router.sys_ethics, "exempt", lambda c: True)
    monkeypatch.setattr(mdl_router, "OpenAICompatLLM", Provider)
    Provider.seen = []
    base = mdl_router.base(cloud_cfg)
    assert isinstance(base, mdl_router.CloudBase) and base.health()
    step = mdl_router.model_for("synthesis", base, cloud_cfg)            # assigned "local": the cloud default
    out = step.complete("sys", "la mail di Mario è mario.rossi@example.com", 50)
    assert "mario.rossi@example.com" not in Provider.seen[0] and "[EMAIL_1]" in Provider.seen[0]
    assert out.answer == "scrivi a mario.rossi@example.com"            # unmasked on the way back


def test_without_the_exemption_nothing_leaves_and_the_reason_is_said(cloud_cfg, monkeypatch):
    monkeypatch.setattr(mdl_router.sys_ethics, "exempt", lambda c: False)
    monkeypatch.setattr(mdl_router, "OpenAICompatLLM", Provider)
    Provider.seen = []
    base = mdl_router.base(cloud_cfg)
    assert "exemption" in base.problem() and not base.health()
    with pytest.raises(RuntimeError, match="exemption"):
        mdl_router.model_for("agent", base, cloud_cfg).complete("sys", "ciao", 10)
    assert Provider.seen == []
    rep = sys_features.check(cloud_cfg, "reasoner")
    assert not rep["ok"] and rep["required"] and "exemption" in rep["missing"][0]


def test_a_missing_key_or_model_is_said_before_any_call(tmp_path, monkeypatch):
    monkeypatch.setattr(mdl_router.sys_ethics, "exempt", lambda c: True)
    c = sys_config.load(write_env(tmp_path, AURORA_LLM_BACKEND="cloud", AURORA_CLOUD_PROVIDER="openai",
                                  AURORA_OPENAI_API_KEY=""), check_root=False)
    assert mdl_router.CloudBase(c).problem() == "AURORA_OPENAI_API_KEY is empty"
    c.values["AURORA_OPENAI_API_KEY"] = "sk-test"
    assert mdl_router.CloudBase(c).problem() == "AURORA_CLOUD_MODEL is empty"


def test_a_local_machine_keeps_its_local_reasoner(cfg):
    from aurora.mdl_llm import LLM
    assert cfg["AURORA_LLM_BACKEND"] == "local" and isinstance(mdl_router.base(cfg), LLM)


def test_the_reasoner_feature_needs_no_model_file_in_the_cloud(cloud_cfg, monkeypatch):
    monkeypatch.setattr(mdl_router.sys_ethics, "exempt", lambda c: True)
    assert sys_features.check(cloud_cfg, "reasoner")["ok"] and sys_features.check(cloud_cfg, "vision")["ok"]
    cloud_cfg.values["AURORA_CLOUD_PROVIDER"] = "claude_code"
    assert not sys_features.check(cloud_cfg, "vision")["ok"]           # the CLI sees no pictures


@pytest.mark.skipif(os.name == "nt", reason="systemd units: Windows writes scheduled tasks (sys_install_tasks.py)")
def test_no_aurora_llm_unit_on_a_cloud_machine(cloud_cfg, monkeypatch, tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "script"))
    import sys_install_services as inst
    monkeypatch.setattr(sys_config, "get", lambda: cloud_cfg)
    from aurora import net_https
    monkeypatch.setattr(net_https.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "", ""))
    stale = cloud_cfg.root / "sys/deploy/systemd/aurora-llm.service"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text("old", encoding="utf-8")
    assert inst.main() == 0
    out = cloud_cfg.root / "sys/deploy/systemd"
    assert not (out / "aurora-llm.service").exists()
    assert "aurora-llm" not in (out / "aurora-api.service").read_text(encoding="utf-8")
    assert "aurora-llm" not in (out / "aurora.target").read_text(encoding="utf-8")
    assert "aurora-llm" not in (out / "install.sh").read_text(encoding="utf-8")
    # the CPU is the owner's desktop too: encoder and harvest give way (a colleague's aurora-models at 187 %)
    for unit in ("aurora-models", "aurora-harvester"):
        assert "Nice=10" in (out / f"{unit}.service").read_text(encoding="utf-8")
    assert "Nice=" not in (out / "aurora-api.service").read_text(encoding="utf-8")


def test_the_profile_without_a_gpu_is_the_cloud_one(monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "script"))
    import sys_profile
    p = sys_profile.choose([], 16.0)
    assert p["cloud"] and p["env"]["AURORA_LLM_BACKEND"] == "cloud"
    assert p["env"]["AURORA_EMBEDDER_DEVICE"] == p["env"]["AURORA_RERANKER_DEVICE"] == "cpu"
    assert int(p["env"]["AURORA_SEARCH_CANDIDATES"]) <= 30             # M151: 30 re-ranked in seconds on a CPU
    small = sys_profile.choose([{"index": 0, "name": "x", "vram_gb": 8.0, "compute_cap": "8.6"}], 16.0)
    assert small["cloud"]                                              # a GPU too small for the reasoner
    schema = {s["key"]: s for s in sys_config.load_schema()["settings"]}
    for k, v in p["env"].items():                                      # every value valid for the schema
        if schema[k]["type"] == "enum":
            assert v in schema[k]["choices"], k


def test_a_gpu_group_is_not_offered_without_a_gpu():
    profile = {"gpus": [], "ram_gb": 16.0}
    assert not sys_features.fits(profile, "voice_natural")[0] and not sys_features.fits(profile, "dreams")[0]
    assert sys_features.fits(profile, "speech")[0] and sys_features.fits(profile, "voice")[0]


def test_the_models_page_says_what_local_is(cloud_cfg, cfg):
    assert "openai m1" in mdl_router.label("local", cloud_cfg) and "openai m1" not in mdl_router.label("local", cfg)
    assert mdl_router.label("google", cloud_cfg) == mdl_router.PROVIDERS["google"]["label"]


def test_a_thinking_model_that_spent_the_budget_is_asked_again(cfg, monkeypatch):
    """C209: gemini-pro-latest cannot stop thinking and counts it in max_tokens: with a short step's 16-32 tokens it
    answered nothing (measured, 8 Oct 2026). A refused reasoning_effort is dropped and remembered."""
    import httpx
    sent = []

    def post(url, headers, timeout, json):
        sent.append(dict(json))
        if "reasoning_effort" in json and json["model"] == "plain":
            return httpx.Response(400, text='{"error": "This model does not support reasoning_effort"}',
                                  request=httpx.Request("POST", url))
        empty = json["max_tokens"] < 100
        return httpx.Response(200, json={"choices": [{"message": {"content": None if empty else "ok"},
                                                      "finish_reason": "length" if empty else "stop"}],
                                         "usage": {"completion_tokens": 0 if empty else 1}},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", post)
    cfg.values["AURORA_GOOGLE_API_KEY"] = "k"
    out = mdl_router.OpenAICompatLLM("google", "pro", cfg).complete("s", "Say: ok", 16)
    assert out.answer == "ok" and sent[0]["max_tokens"] == 16 and sent[1]["max_tokens"] == 16 + 4096
    assert sent[0]["reasoning_effort"] == "low"
    sent.clear()
    m = mdl_router.OpenAICompatLLM("google", "plain", cfg)
    assert m.complete("s", "x", 500).answer == "ok" and "reasoning_effort" not in sent[-1]
    sent.clear()
    m.complete("s", "x", 500)
    assert len(sent) == 1 and "reasoning_effort" not in sent[0]       # remembered: not tried again


def test_a_few_words_left_by_the_thinking_are_asked_again(cfg, monkeypatch):
    """C230 (the Windows VM, 9 Oct): gemini-pro-latest thought 190 of 200 tokens and the standalone question came back
    «La mia mail è [EMAIL» — cut, not empty. A truncation that is mostly thinking is asked again; a long answer cut
    at its own length is not."""
    import httpx
    sent = []

    def post(url, headers, timeout, json):
        sent.append(dict(json))
        small = json["max_tokens"] <= 200
        text, visible = ("La mia mail è [EMAIL", 6) if small else ("La mia mail è [EMAIL_1]. Che cos'è un solitone?", 14)
        thought = 190 if small else 300
        if json.get("model") == "long":
            text, visible, thought = "x " * 200, 200, 0
        return httpx.Response(200, json={"choices": [{"message": {"content": text},
                                                      "finish_reason": "length" if small else "stop"}],
                                         "usage": {"prompt_tokens": 490, "completion_tokens": visible,
                                                   "total_tokens": 490 + visible + thought}},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", post)
    cfg.values["AURORA_GOOGLE_API_KEY"] = "k"
    out = mdl_router.OpenAICompatLLM("google", "pro", cfg).complete("s", "q", 200)
    assert out.answer.endswith("solitone?") and [x["max_tokens"] for x in sent] == [200, 200 + 4096]
    sent.clear()
    out = mdl_router.OpenAICompatLLM("google", "long", cfg).complete("s", "q", 200)
    assert len(sent) == 1 and out.truncated


def test_the_installers_trial_call_needs_no_env_file(tmp_path):
    """The installer proves the provider before any .env exists: the trial read the missing .env through the log and
    stopped every installation without a GPU (a clean clone, 8 Oct 2026)."""
    stub = tmp_path / "claude"
    stub.write_text('#!/usr/bin/env python3\nimport json, sys\nsys.stdin.read()\n'
                    'print(json.dumps({"result": "ok", "usage": {}, "is_error": False}))\n', encoding="utf-8")
    stub.chmod(0o755)
    import os
    if os.name == "nt":                               # Windows runs no script without an extension: claude.cmd, as npm's
        (tmp_path / "claude.cmd").write_text(f'@"{sys.executable}" "{stub}" %*\r\n', encoding="utf-8")
    env = {**os.environ, "AURORA_ENV_FILE": str(tmp_path / "missing.env"), "AURORA_INSTALL_CLOUD_KEY": "",
           "PATH": f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}"}
    script = Path(__file__).resolve().parents[1] / "script" / "sys_cloud_setup.py"
    r = subprocess.run([sys.executable, str(script), "try", "claude_code", "sonnet"], env=env, cwd=tmp_path,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    assert r.stdout.strip() == "ok", r.stdout + r.stderr


def test_any_openai_compatible_service_with_or_without_a_key(cfg, monkeypatch):
    """Provider 'custom': its address is a setting, its key may be empty (a company server, vLLM, LM Studio)."""
    import httpx
    cfg.values.update(AURORA_CUSTOM_BASE_URL="", AURORA_CUSTOM_API_KEY="")
    assert not mdl_router.configured("custom", cfg)
    cfg.values["AURORA_CUSTOM_BASE_URL"] = "http://server.lan:8000/v1/"
    assert mdl_router.configured("custom", cfg) and mdl_router.base_url("custom", cfg) == "http://server.lan:8000/v1"
    seen = []

    def post(url, headers, timeout, json):
        seen.append((url, dict(headers)))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}], "usage": {}},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", post)
    assert mdl_router.OpenAICompatLLM("custom", "m", cfg).complete("s", "u", 50).answer == "ok"
    assert seen[0][0] == "http://server.lan:8000/v1/chat/completions" and "Authorization" not in seen[0][1]
    cfg.values["AURORA_CUSTOM_API_KEY"] = "k"
    mdl_router.OpenAICompatLLM("custom", "m", cfg).complete("s", "u", 50)
    assert seen[1][1]["Authorization"] == "Bearer k"
    cfg.values.update(AURORA_LLM_BACKEND="cloud", AURORA_CLOUD_PROVIDER="custom", AURORA_CLOUD_MODEL="m",
                      AURORA_CUSTOM_BASE_URL="")
    monkeypatch.setattr(mdl_router.sys_ethics, "exempt", lambda c: True)
    assert mdl_router.CloudBase(cfg).problem() == "AURORA_CUSTOM_BASE_URL is empty"
    assert set(mdl_router.PROVIDERS) - {"local"} <= set(sys_config.load_schema()["settings"][
        [s["key"] for s in sys_config.load_schema()["settings"]].index("AURORA_CLOUD_PROVIDER")]["choices"])
