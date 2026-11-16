# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The night's work made up by day (owner, 17 Nov: Aurora switched off at night — the dream, the study, the shadow's
training, the deductions and the vault's check must not be lost)."""
import importlib
import sys
from datetime import datetime
from pathlib import Path

import pytest

from aurora import sys_config


@pytest.fixture
def rem(cfg, monkeypatch):
    cfg.values.update(AURORA_REM_DREAM_HOURS="2-6", AURORA_REM_IDLE_MIN=20, AURORA_MOOD_STRESS_PAUSE=0.9)
    monkeypatch.setattr(sys_config, "get", lambda *a, **k: cfg)
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "script"))
    sys.modules.pop("svc_rem", None)
    m = importlib.import_module("svc_rem")
    yield m
    sys.modules.pop("svc_rem", None)


def _st(dream, **due):
    return {"idle_min": 60, "sessions_to_consolidate": 0, "last": {"dream": dream, "thought": None}, **due}


def at(rem, monkeypatch, when):
    monkeypatch.setattr(rem.sns_clock, "now", lambda cfg: datetime.fromisoformat(when))


def test_a_night_spent_switched_off_is_made_up_when_she_is_silent(rem, monkeypatch):
    at(rem, monkeypatch, "2026-11-17T10:00:00")
    assert rem.choose(_st("2026-11-16T03:00:00"))[0] == "dream"                       # off last night
    # the dream made up at 10:05: the rest of the night follows, each once
    st = _st("2026-11-17T10:05:00", to_study=3, studied_tonight=False, train_due=True, deduce_due=True, audit_due=True)
    assert rem.choose(st)[0] == "study"
    assert rem.choose({**st, "studied_tonight": True})[0] == "train"
    assert rem.choose({**st, "studied_tonight": True, "train_due": False, "deduce_due": False})[0] == "audit"


def test_a_night_done_in_its_window_owes_nothing_by_day(rem, monkeypatch):
    at(rem, monkeypatch, "2026-11-17T10:00:00")
    st = _st("2026-11-17T02:40:00", to_study=3, studied_tonight=False, train_due=True, audit_due=True)
    assert rem.choose(st)[0] not in ("dream", "study", "train", "deduce", "audit")


def test_the_window_itself_works_as_before(rem, monkeypatch):
    at(rem, monkeypatch, "2026-11-17T03:00:00")
    assert rem.choose(_st("2026-11-16T02:30:00"))[0] == "dream"
    assert not rem.owed_night("2026-11-16T02:30:00", datetime.fromisoformat("2026-11-17T03:00:00"))


def test_the_owner_talking_still_comes_first(rem, monkeypatch):
    at(rem, monkeypatch, "2026-11-17T10:00:00")
    assert rem.choose({**_st("2026-11-15T03:00:00"), "idle_min": 5})[0] is None


def test_the_vaults_confirmed_fix_runs_once_and_is_told(rem, monkeypatch):
    """C607: aurora-rem runs what the nightly check confirmed, then says what was done."""
    import subprocess
    from types import SimpleNamespace

    from aurora import kno_vault_audit
    argv = [["/x/vault_realign.py", "--wikipedia", "--only", "wikipedia:Town 1", "--apply"]]
    monkeypatch.setattr(kno_vault_audit, "fix_argv", lambda cfg: argv)
    marked, posted, ran = [], [], []
    monkeypatch.setattr(kno_vault_audit, "mark_fixed", lambda cfg, r: marked.append(r))
    monkeypatch.setattr(subprocess, "run", lambda a, **k: ran.append(a) or SimpleNamespace(
        returncode=0, stdout="Wikipedia articles: 1 · fine 0 · to move 1\n", stderr=""))
    client = SimpleNamespace(post=lambda url, json: posted.append(json))
    rem.vault_fix(client)
    assert ran[0][1:] == argv[0] and marked[0][0]["ok"]
    assert posted[0]["event"] == "vault.fixed" and "to move 1" in posted[0]["payload"]["text"]
