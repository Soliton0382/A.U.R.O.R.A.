# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Health, sealed (owner, 2026-10-05): what is on the disk is unreadable, another user's key does not open it, a
changed file does not open, a deletion is final, and the agent refuses the private plugin to a cloud model."""
import json

import pytest

from aurora import hlt_store, sys_seal
from conftest import private  # noqa: E402 — who may read a file, asked of this system


def test_documents_and_notes_are_sealed_on_the_disk(cfg):
    it = hlt_store.add_document(cfg, "diet", "piano.txt", "Pranzo: riso integrale 80 g, verdure.".encode())
    hlt_store.add_note(cfg, "training", "corsa", "40 minuti di corsa, 6 km")
    files = [p for p in cfg.path("AURORA_HEALTH_DIR").rglob("*") if p.is_file()]
    assert files and all(f.read_bytes().startswith(sys_seal.MAGIC) for f in files)
    assert not any(b"riso" in f.read_bytes() or b"corsa" in f.read_bytes() for f in files)
    assert "riso integrale" in hlt_store.text(cfg, "diet", it["id"])
    assert hlt_store.original(cfg, "diet", it["id"])[1].startswith(b"Pranzo")
    assert "6 km" in hlt_store.everything(cfg, "training")
    key = sys_seal._key(cfg, cfg.user, "health")
    assert len(key) == 32 and private(sys_seal.L.place(cfg, "state", cfg.user) / "keys" / "health.key")


def test_a_changed_or_swapped_file_or_another_key_does_not_open(cfg):
    blob = sys_seal.seal(cfg, b"colesterolo 180", "a.sealed")
    with pytest.raises(ValueError):
        sys_seal.unseal(cfg, blob, "b.sealed")                      # bound to its name
    bad = blob[:-1] + bytes([blob[-1] ^ 1])
    with pytest.raises(ValueError):
        sys_seal.unseal(cfg, bad, "a.sealed")                       # changed
    with pytest.raises(ValueError):
        sys_seal.unseal(cfg, blob, "a.sealed", purpose="other")      # another key
    assert sys_seal.unseal(cfg, blob, "a.sealed") == b"colesterolo 180"


def test_a_deletion_is_final(cfg):
    it = hlt_store.add_document(cfg, "exams", "esame.txt", b"Glicemia 92 mg/dl")
    hlt_store.delete(cfg, "exams", it["id"])
    assert hlt_store.items(cfg, "exams") == []
    assert [p.name for p in (cfg.path("AURORA_HEALTH_DIR") / "exams").iterdir()] == ["index.sealed"]
    with pytest.raises(ValueError):
        hlt_store.add_note(cfg, "exams", "", "  ")
    with pytest.raises(ValueError):
        hlt_store.items(cfg, "wallet")


def test_the_health_plugin_is_private():
    from pathlib import Path
    m = json.loads((Path(__file__).resolve().parents[2] / "plugins" / "health" / "plugin.json").read_text())
    assert m["private"] is True and m["sandbox"]["network"] is False


def test_private_data_moves_the_agent_to_the_local_model(cfg):
    """2026-10-06: «a che ora ho il medico?» was refused because the agent ran on a cloud model; now the run goes on
    with the local model from the moment private data is read — the cloud model never sees it."""
    from types import SimpleNamespace
    from aurora.agt_loop import Agent
    local, cloud = object(), object()
    called, events = [], []
    host = SimpleNamespace(get=lambda name: SimpleNamespace(manifest={"private": True, "effects": {"*": "read"}}),
                           call=lambda *a, **k: called.append(a) or {"ok": True, "text": "dati"})
    index = {"health__health_read": ("health", "health_read", "read")}
    p = SimpleNamespace(llm=local, _for=lambda role: cloud)
    a = Agent(p, cfg, host=host)
    assert a._model() is cloud
    out = a._call("health__health_read", {"area": "diet"}, index, lambda e, d: events.append(e), "r1")
    assert out == "dati" and len(called) == 1 and "agent.local" in events
    assert a.local_only and a._model() is local                     # every next step: the local model


def test_without_a_local_model_private_data_is_not_even_read(tmp_path, monkeypatch):
    """C213: on a cloud-only installation the «local» model is the cloud's: the health plugin is not called at all, the
    exam values are not read by a model, the diet plan comes without the model's summary, the firewall plans nothing."""
    from types import SimpleNamespace
    from aurora import mdl_router, sec_fwplan, sec_fwwrite, sys_config
    from aurora.agt_loop import Agent
    from conftest import write_env
    cloud_cfg = sys_config.load(write_env(tmp_path, AURORA_LLM_BACKEND="cloud"), check_root=False)
    base = mdl_router.base(cloud_cfg)
    assert mdl_router.private_model(base, cloud_cfg) is None
    assert mdl_router.private_model(mdl_router.model_for("agent", base, cloud_cfg), cloud_cfg) is None
    called, events = [], []
    host = SimpleNamespace(get=lambda name: SimpleNamespace(manifest={"private": True, "effects": {"*": "read"}}),
                           call=lambda *a, **k: called.append(a) or {"ok": True, "text": "dati"})
    p = SimpleNamespace(llm=base, _for=lambda role: base)
    a = Agent(p, cloud_cfg, host=host)
    out = a._call("health__health_read", {"area": "diet"}, {"health__health_read": ("health", "health_read", "read")},
                  lambda e, d: events.append(e), "r1")
    assert out.startswith("ERROR") and called == [] and "agent.private_refused" in events
    with pytest.raises(sec_fwwrite.WriteError, match="modello locale"):
        sec_fwplan.plan(cloud_cfg, "blocca il traffico verso 10.0.0.9", conf={})


def test_a_local_model_is_still_the_private_one(cfg):
    from aurora import mdl_router
    local = object()
    assert mdl_router.private_model(local, cfg) is local
