# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""☀️ Oggi: the day's headlines (every 3 hours) and the research routines' last report (owner, 16 Oct)."""
from pathlib import Path

from aurora.txt_headlines import headlines, key

TEXT = """Notizie: mondo, ultime 12 ore (2)
- [16/10 11:40] Un titolo del mondo — BBC
  Il sommario breve.
  https://example.org/a
- [16/10 10:05] Un altro titolo — The Guardian
  Altro sommario.
  https://example.org/b"""


def test_the_news_plugin_rows_become_headlines():
    h = headlines(TEXT)
    assert [x["title"] for x in h] == ["Un titolo del mondo", "Un altro titolo"]
    assert h[0] == {"when": "16/10 11:40", "title": "Un titolo del mondo", "source": "BBC", "summary": "Il sommario breve.",
                    "link": "https://example.org/a"}
    assert headlines("nessuna notizia nel periodo") == [] and key("Un  titolo!") == key("un titolo")
    src = (Path(__file__).resolve().parents[1] / "aurora" / "api" / "today.py").read_text(encoding="utf-8")
    assert "EVERY_S = 3 * 3600" in src                           # the owner's «aggiornate ogni 3 ore»
