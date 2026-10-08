# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The whole of Aurora as one choice (mdl_modes): local, mixed, cloud with privacy, all cloud. Every cloud mode needs
the exemption; «all cloud» needs the owner's consent signed from a shell and is taken back from the web; private data
stays on a local model in every mode where there is one; the local reasoner switched off and on."""
import subprocess
import sys
from pathlib import Path

import pytest

from aurora import mdl_media, mdl_modes, mdl_router, sys_cloud_consent, sys_config, sys_ethics

from conftest import write_env


@pytest.fixture
def machine(tmp_path, monkeypatch):
    """A machine with a local reasoner and an OpenAI key; exemption and consent decided by the test."""
    cfg = sys_config.load(write_env(tmp_path, AURORA_OPENAI_API_KEY="sk-test", AURORA_ANTHROPIC_API_KEY=""),
                          check_root=False)                 # the cloud default (anthropic) without its key
    state = {"exempt": False, "consent": False}
    monkeypatch.setattr(sys_ethics, "exempt", lambda c=None: state["exempt"])
    monkeypatch.setattr(sys_cloud_consent, "signed", lambda c: state["consent"])
    monkeypatch.setattr(mdl_modes, "local_reasoner", lambda c: not mdl_router.cloud_only(c))
    return cfg, state


def test_a_new_machine_is_local_and_the_table_says_what_stays_here(machine):
    cfg, _ = machine
    out = mdl_modes.check(cfg)
    assert out["mode"] == "local" and out["exempt"] is False
    rows = {r["id"]: r for r in out["aspects"]}
    assert rows["search"]["modes"]["cloud_full"]["state"] == "stay"          # no cloud version, ever
    assert rows["private"]["modes"]["cloud_private"]["state"] == "stay"
    assert {n["need"] for n in out["needs"]} == {"exempt", "key", "consent"}     # anthropic, the default, has no key
    assert next(n for n in out["needs"] if n["need"] == "consent")["command"] == sys_cloud_consent.COMMAND


def test_cloud_with_privacy_needs_the_exemption_then_moves_every_role(machine):
    cfg, state = machine
    with pytest.raises(mdl_modes.ModeError) as e:
        mdl_modes.apply(cfg, "cloud_private", "openai", "gpt-x")
    assert e.value.need == "exempt" and "sys_ethics_sign.py exempt" in e.value.command
    state["exempt"] = True
    with pytest.raises(mdl_modes.ModeError, match="modello"):
        mdl_modes.apply(cfg, "cloud_private", "openai", "")
    out = mdl_modes.apply(cfg, "cloud_private", "openai", "gpt-x")
    roles = mdl_router.assignments(cfg)
    assert out["mode"] == "cloud_private" and set(roles) >= {"service", "vision", "agent"}
    assert all(a == {"provider": "openai", "model": "gpt-x"} for a in roles.values())
    media = mdl_media.assignments(cfg)
    assert media["image"]["provider"] == "openai" and media["video"]["provider"] == "local"     # OpenAI makes no video
    now = mdl_modes.now(cfg)
    assert now["AURORA_CLOUD_PROVIDER"] == "openai" and now["AURORA_CLOUD_MODEL"] == "gpt-x"
    assert mdl_modes.current(cfg) == "cloud_private"


def test_all_cloud_asks_the_shell_and_privacy_takes_it_back_from_the_web(machine):
    cfg, state = machine
    state["exempt"] = True
    with pytest.raises(mdl_modes.ModeError) as e:
        mdl_modes.apply(cfg, "cloud_full", "openai", "gpt-x")
    assert e.value.need == "consent" and e.value.command == sys_cloud_consent.COMMAND
    state["consent"] = True
    assert mdl_modes.apply(cfg, "cloud_full", "openai", "gpt-x")["mode"] == "cloud_full"
    f = sys_cloud_consent.path(cfg)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("sig")
    mdl_modes.apply(cfg, "cloud_private", "openai", "gpt-x")
    assert not f.exists()                                   # back to privacy: no shell needed
    f.write_text("sig")
    mdl_modes.apply(cfg, "local")
    assert not f.exists() and mdl_modes.current(cfg) == "local"
    assert all(a["provider"] == "local" for a in mdl_router.assignments(cfg).values())


def test_claude_code_keeps_the_pictures_local(machine):
    cfg, state = machine
    state["exempt"] = True
    mdl_modes.apply(cfg, "cloud_private", "claude_code", "sonnet")
    roles = mdl_router.assignments(cfg)
    assert roles["vision"]["provider"] == "local" and roles["agent"]["provider"] == "claude_code"
    assert mdl_modes.current(cfg) == "cloud_private"


def test_private_data_follows_the_consent_only_where_no_local_model_runs(tmp_path, monkeypatch):
    cfg = sys_config.load(write_env(tmp_path, AURORA_LLM_BACKEND="cloud", AURORA_CLOUD_PROVIDER="openai",
                                    AURORA_CLOUD_MODEL="m", AURORA_OPENAI_API_KEY="k"), check_root=False)
    monkeypatch.setattr(sys_ethics, "exempt", lambda c=None: True)
    base = mdl_router.base(cfg)
    monkeypatch.setattr(sys_cloud_consent, "signed", lambda c: False)
    assert mdl_router.private_model(base, cfg) is None
    monkeypatch.setattr(sys_cloud_consent, "signed", lambda c: True)
    assert mdl_router.private_model(base, cfg) is base
    local = object()
    (tmp_path / "l").mkdir()
    local_cfg = sys_config.load(write_env(tmp_path / "l"), check_root=False)
    assert mdl_router.private_model(local, local_cfg) is local          # a local model: always it, consent or not


def test_the_local_reasoner_off_and_on(machine, monkeypatch):
    cfg, state = machine
    calls = []
    run = lambda cmd, **k: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0, "", "")   # noqa: E731
    with pytest.raises(mdl_modes.ModeError) as e:
        mdl_modes.reasoner(cfg, False, run)
    assert e.value.need == "exempt"
    state["exempt"] = True
    with pytest.raises(mdl_modes.ModeError, match="provider cloud"):   # the cloud default has no model yet
        mdl_modes.reasoner(cfg, False, run)
    sys_config.write_env(cfg.env_file, {"AURORA_CLOUD_MODEL": "gpt-x", "AURORA_CLOUD_PROVIDER": "openai"})
    out = mdl_modes.reasoner(cfg, False, run)
    assert out["backend"] == "cloud" and calls[-1] == ["systemctl", "stop", "aurora-llm"]
    assert mdl_modes.now(cfg)["AURORA_LLM_BACKEND"] == "cloud"
    with pytest.raises(mdl_modes.ModeError) as e:                      # no model on disk: install.sh
        mdl_modes.reasoner(cfg, True, run)
    assert e.value.need == "local_model"
    bad = lambda cmd, **k: subprocess.CompletedProcess(cmd, 1, "", "denied")   # noqa: E731
    monkeypatch.setattr(mdl_modes, "can_have_local", lambda c: True)
    from aurora import sys_health
    monkeypatch.setattr(sys_health, "gpu_job", lambda c: "")
    with pytest.raises(mdl_modes.ModeError, match="denied"):
        mdl_modes.reasoner(cfg, True, bad)
    assert mdl_modes.now(cfg)["AURORA_LLM_BACKEND"] == "cloud"           # put back as it was
    monkeypatch.setattr(sys_health, "gpu_job", lambda c: "video since 10:00:00")
    with pytest.raises(mdl_modes.ModeError, match="GPU"):
        mdl_modes.reasoner(cfg, True, run)                             # rule 6


def test_the_reasoners_service_stays_down_with_the_cloud(tmp_path, monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "script"))
    import svc_llm
    cfg = sys_config.load(write_env(tmp_path, AURORA_LLM_BACKEND="cloud"), check_root=False)
    monkeypatch.setattr(sys_config, "get", lambda: cfg)
    monkeypatch.setattr(svc_llm.subprocess, "Popen", lambda *a, **k: pytest.fail("llama-server started"))
    assert svc_llm.main() == 0


def test_the_forge_asks_the_chosen_cloud(machine, monkeypatch):
    cfg, _ = machine
    from aurora import mdl_cloud
    assert isinstance(mdl_router.forge_cloud(cfg), mdl_cloud.ClaudeCodeLLM)          # nothing chosen: Claude Code
    mdl_router.set_assignments(cfg, {"forge_write": {"provider": "openai", "model": "gpt-x"}})
    client = mdl_router.forge_cloud(cfg)
    assert isinstance(client, mdl_router.OpenAICompatLLM) and client.model == "gpt-x"


def test_a_few_steps_in_the_cloud_is_mixed(machine):
    """The owner's own machine (8 Oct): the agent and the forge on Claude Code, the rest local — «mixed», not cloud."""
    cfg, _ = machine
    mdl_router.set_assignments(cfg, {"agent": {"provider": "claude_code", "model": ""},
                                     "forge_write": {"provider": "claude_code", "model": "opus"}})
    assert mdl_modes.current(cfg) == "mixed"
