# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The conductor of a project (prj_conduct, N39): the owner's words become a draft goal built on the project's open
items; the reply comes after the run; a «local» project is conducted by the local model only."""
from types import SimpleNamespace

import pytest

from aurora import prj_conduct as C
from aurora import prj_policy


class _LLM:
    def __init__(self, answer):
        self.answer, self.seen = answer, []

    def complete(self, system, user, max_tokens, think=False):
        self.seen.append((system, user))
        return SimpleNamespace(answer=self.answer)


@pytest.fixture
def project(cfg):
    p = cfg.path("AURORA_PROJECTS_DIR") / "motore"
    (p / "docs").mkdir(parents=True, exist_ok=True)
    (p / "docs" / "DA_FARE.md").write_text("# DA FARE\n- [ ] misurare la coppia a 3000 giri\n", encoding="utf-8")
    (p / "docs" / "01_scheda.md").write_text("# scheda\n", encoding="utf-8")
    return "motore"


def test_the_owner_words_become_a_draft_built_on_the_open_items(cfg, project):
    llm = _LLM("  Progetto «motore»: 1. misura la coppia.  ")
    g = C.draft(cfg, project, "proviamo la coppia ad alta velocita", llm)
    assert g["kind"] == "goal" and g["status"] == "draft" and g["text"] == "Progetto «motore»: 1. misura la coppia."
    system, user = llm.seen[0]
    assert "motore" in system and "misurare la coppia a 3000 giri" in user and "01_scheda.md" in user
    assert "proviamo la coppia ad alta velocita" in user
    assert [e["kind"] for e in C.history(cfg, project)] == ["ask", "goal"]


def test_a_started_draft_keeps_its_changed_text_and_the_reply_follows(cfg, project):
    g = C.draft(cfg, project, "fase uno", _LLM("obiettivo"))
    C.update(cfg, project, g["id"], status="running", text="obiettivo cambiato")
    r = C.review(cfg, project, "obiettivo cambiato", "Fatto: coppia 1.2 N m.", _LLM("1. Fatto: 1.2 N m"))
    items = C.history(cfg, project)
    assert items[1]["text"] == "obiettivo cambiato" and items[1]["status"] == "running"
    assert items[-1] == r and r["kind"] == "reply"
    assert "fase uno" in C.context(cfg, project)                                 # the next draft reads the talk


def test_a_local_project_is_conducted_by_the_local_model(cfg, project):
    p = SimpleNamespace(llm="locale", _for=lambda role: "cloud mascherato")
    assert C.model(cfg, project, p) == "cloud mascherato"
    prj_policy.save(cfg, project, {"models": "local", "publish": False})
    assert C.model(cfg, project, p) == "locale"


def test_only_real_projects(cfg):
    with pytest.raises(ValueError):
        C.context(cfg, "../fuori")
    with pytest.raises(ValueError):
        C.context(cfg, "manca")


class _Down:
    def complete(self, system, user, max_tokens, think=False):
        raise RuntimeError("claude -p: You've hit your session limit")


def test_the_cloud_judge_out_the_local_model_drafts(cfg, project):
    g = C.draft(cfg, project, "fase con il cloud esaurito", _Down(), fallback=_LLM("obiettivo locale"))
    assert g["text"] == "obiettivo locale" and [e["kind"] for e in C.history(cfg, project)] == ["ask", "goal"]
    with pytest.raises(RuntimeError):
        C.draft(cfg, project, "senza riserva", _Down())
