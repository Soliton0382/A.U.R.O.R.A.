# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Dynamic masking (sec_mask_spot, 28 Oct): what the local model names as private is masked before the text leaves
and learnt for the next time; whole words only; the rules «F. Surname» and «Dott. Name» always, and alone when the
local model cannot be asked (then nothing is learnt); Aurora's users' names masked, a common one only in usr/<name>.
The model here is a stand-in; the live trial is in MEASUREMENTS (M267)."""
from aurora import sec_mask_spot as S
from aurora.sec_mask import Pseudonymizer


def _model(monkeypatch, answer):
    asked = []

    def ask(cfg, chunk):
        asked.append(chunk)
        return answer(chunk) if callable(answer) else answer
    monkeypatch.setattr(S, "_ask", ask)
    S._seen.clear()
    return asked


def test_what_the_local_model_names_is_masked_and_learnt(cfg, monkeypatch):
    asked = _model(monkeypatch, lambda chunk: [w for w in ("Marco Bellini", "Borgo Fiorito") if w in chunk])
    p = Pseudonymizer(cfg)
    out = p.mask("Ne ho parlato con Marco Bellini a Borgo Fiorito; la matrice di Hadamard resta.")
    assert "Bellini" not in out and "Borgo Fiorito" not in out and "Hadamard" in out
    assert p.unmask(out) == "Ne ho parlato con Marco Bellini a Borgo Fiorito; la matrice di Hadamard resta."
    assert set(S.learned(cfg)) == {"Marco Bellini", "Borgo Fiorito"}
    p.mask("Ne ho parlato con Marco Bellini a Borgo Fiorito; la matrice di Hadamard resta.")
    assert len(asked) == 1                                                       # the same chunk: asked once
    _model(monkeypatch, None)                                                    # the model down: still masked
    assert "Bellini" not in Pseudonymizer(cfg).mask("Domani vedo Marco Bellini.")
    assert S.forget(cfg, "Borgo Fiorito") and S.learned(cfg) == ["Marco Bellini"]


def test_the_rules_beside_the_model_and_alone(cfg, monkeypatch):
    _model(monkeypatch, [])                                                      # the model saw nothing
    out = Pseudonymizer(cfg).mask("Il paper di F. Rossi (2026) e i conti del dott. Neri; le funzioni di Walsh.")
    assert "Rossi" not in out and "Neri" not in out and "Walsh" in out
    _model(monkeypatch, None)                                                    # down: the rules alone, nothing learnt
    assert "Bianchi" not in Pseudonymizer(cfg).mask("Firmato: ing. Bianchi") and S.learned(cfg) == []


def test_whole_words_and_the_users_names(cfg, monkeypatch):
    from aurora.sys_users import Users
    u = Users(cfg)
    u.add("test", "admin", "a long password")
    u.add("Ludovica", "user", "another long password")
    _model(monkeypatch, [])
    out = Pseudonymizer(cfg).mask("pytest in usr/test/projects; Ludovica scrive; Ludovicamente no; test passed")
    assert "pytest" in out and "test passed" in out and "usr/test/" not in out           # a common name: its path only
    assert "Ludovica scrive" not in out and "Ludovicamente" in out
    cfg.values["AURORA_CLOUD_MASK_DYNAMIC"] = False
    assert S.spot(cfg, "Marco Bellini") == ([], True)
