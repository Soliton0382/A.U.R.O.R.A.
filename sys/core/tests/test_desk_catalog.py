# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N157 phase A: the chat knows what Aurora learned on a desktop — the general library listed and explained, read
only, offered when the request speaks of the desktop, never in the anonymous chat; it says it does not act yet."""
from aurora import desk_catalog as D, sys_context


def test_the_general_library_is_listed_and_each_procedure_explained():
    out = D.listing()
    assert "gen:linux/kate/scrivi-e-salva" in out and "gen:linux/kcalc/calcola" in out and "does NOT perform" in out
    det = D.detail("gen:linux/kate/scrivi-e-salva")
    assert "1. scrivi {testo} nel campo" in det and "[scrive in locale]" in det and "testo (text, max 2000)" in det
    assert D.detail("gen:nessuna").startswith("ERROR")


def test_offered_only_when_the_desktop_is_meant_and_never_anonymously(cfg, monkeypatch):
    monkeypatch.setattr(sys_context, "anonymous_now", lambda: False)
    assert D.offered(cfg, "cosa sai fare sul desktop?") == [D.TOOL]
    assert D.offered(cfg, "apri kate e salva una nota") == [D.TOOL]
    assert D.offered(cfg, "che tempo fa domani?") == []
    monkeypatch.setattr(sys_context, "anonymous_now", lambda: True)
    assert D.offered(cfg, "cosa sai fare sul desktop?") == []


def test_the_tool_reads_nothing_outside_the_general_library():
    assert D.LIBRARY.name == "library" and D.LIBRARY.parent.name == "desk"
    assert all(p["id"].startswith("gen:") for p in D.procedures())
