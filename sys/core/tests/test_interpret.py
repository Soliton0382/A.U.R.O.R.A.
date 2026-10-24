# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🌍 The interpreter (ROADMAP N44): the languages checked, the context given, only the translation kept."""
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from aurora import kno_interpret as I

ROOT = Path(__file__).resolve().parents[1]


def test_the_languages_are_checked():
    assert I.check("IT", "en_US") == ("it", "en")
    with pytest.raises(ValueError):
        I.check("it", "it")
    with pytest.raises(ValueError):
        I.check("it", "xx")


def test_the_sentence_is_translated_with_the_last_lines_for_context():
    seen = {}

    def complete(system, user, max_tokens, think=False):
        seen.update(system=system, user=user, think=think)
        return SimpleNamespace(answer="<text>Where is the station?</text>")
    before = [f"riga {n}" for n in range(9)]
    out = I.translate(SimpleNamespace(complete=complete), "Dov'è la stazione?", "it", "en", before)
    assert out == "Where is the station?"                      # the tags the model copied are dropped
    assert "Italian sentence" in seen["system"] and "into English" in seen["system"] and seen["think"] is False
    assert "riga 4" not in seen["user"] and "riga 5" in seen["user"] and "riga 8" in seen["user"]   # the last 4
    assert seen["user"].endswith("<text>\nDov'è la stazione?\n</text>")
    assert I.translate(SimpleNamespace(complete=complete), "  ", "it", "en") == ""     # nothing said: no call


def test_the_route_needs_a_login_and_keeps_nothing():
    src = (ROOT / "aurora" / "api" / "interpret.py").read_text()
    assert re.findall(r'@router\.\w+\("([^"]+)", dependencies=\[Depends\((\w+)\)\]\)', src) == [("/v1/aurora/interpret", "auth")]
    assert ".remember(" not in src and ".writer" not in src       # no memory, no conversation
    assert "interpret" in (ROOT / "aurora" / "api" / "__init__.py").read_text()


def test_the_page_is_in_the_menu_and_in_the_offline_shell():
    assert 'import interpret from "./modules/interpret.js"' in (ROOT / "webui" / "js" / "modules.js").read_text()
    sw = (ROOT / "webui" / "sw.js").read_text()
    assert "/static/js/modules/interpret.js" in sw and "/static/css/interpret.css" in sw
    for loc in ("it_IT", "en_US"):
        keys = json.loads((ROOT / "webui" / "i18n" / f"{loc}.json").read_text())
        used = set(re.findall(r'(?:t\(|data-i18n=)"(interpret\.[\w.]+)"',
                              (ROOT / "webui" / "js" / "modules" / "interpret.js").read_text()))
        assert used and used <= set(keys) and "nav.interpret" in keys
