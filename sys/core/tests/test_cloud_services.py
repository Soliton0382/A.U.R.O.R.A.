# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Services of one's own, OpenAI-compatible (owner, 15 Oct: Ollama, Kimi…): named, several, removable — the built-in
providers never."""
import pytest

from aurora import mdl_accounts, mdl_router, mdl_services


@pytest.fixture(autouse=True)
def clean_table():
    yield
    for k in [k for k in mdl_router.PROVIDERS if k.startswith(mdl_services.PREFIX)]:
        del mdl_router.PROVIDERS[k]


def test_a_named_service_joins_the_providers_and_goes_out_masked(cfg, monkeypatch):
    a = mdl_services.add(cfg, "Ollama salotto", "http://localhost:11434/v1/")
    b = mdl_services.add(cfg, "Ollama salotto", "http://192.168.1.20:11434/v1")
    assert (a["id"], b["id"]) == ("svc_ollama_salotto", "svc_ollama_salotto_2")      # two of the same name: both kept
    assert mdl_router.base_url(a["id"], cfg) == "http://localhost:11434/v1" and mdl_router.configured(a["id"], cfg)
    client = mdl_router.cloud_client(a["id"], "llama3", cfg)
    assert isinstance(client, mdl_router.OpenAICompatLLM) and client.key == ""         # Ollama asks no key
    monkeypatch.setattr(mdl_router.sys_ethics, "exempt", lambda c: True)
    monkeypatch.setattr(mdl_router, "assignments", lambda c: {"agent": {"provider": a["id"], "model": "llama3"}})
    assert isinstance(mdl_router.model_for("agent", object(), cfg).primary, mdl_router.MaskedLLM)
    with pytest.raises(ValueError):
        mdl_services.add(cfg, "Kimi", "ftp://moonshot")


def test_a_service_s_key_is_an_account_and_goes_with_it(cfg):
    k = mdl_services.add(cfg, "Kimi (Moonshot)", "https://api.moonshot.ai/v1")
    mdl_accounts.add(cfg, k["id"], "shared", None, "Kimi", "sk-kimi-12345678")
    assert mdl_router.OpenAICompatLLM(k["id"], "kimi-k2", cfg).key == "sk-kimi-12345678"
    mdl_services.remove(cfg, k["id"])
    assert k["id"] not in mdl_router.PROVIDERS and not mdl_accounts.load(cfg)["accounts"]


def test_the_built_in_providers_are_never_removed_and_another_process_sees_a_change(cfg):
    with pytest.raises(ValueError):
        mdl_services.remove(cfg, "openai")
    with pytest.raises(KeyError):
        mdl_services.remove(cfg, "svc_nothing")
    import json
    import os
    mdl_services._file(cfg).parent.mkdir(parents=True, exist_ok=True)
    mdl_services._file(cfg).write_text(json.dumps([{"id": "svc_groq", "name": "Groq", "base": "https://api.groq.com/openai/v1"}]))
    os.utime(mdl_services._file(cfg), (1, 1))                                          # written by another process
    assert mdl_router.configured("svc_groq", cfg) and mdl_router.PROVIDERS["svc_groq"]["label"] == "Groq"
