# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The menu's styles (ROADMAP 107): every page of the short menu exists, Oggi and Avanzate are pages, the three styles
have their words in both languages."""
import json
import re
from pathlib import Path

WEBUI = Path(__file__).resolve().parents[1] / "webui"


def test_the_short_menu_holds_only_real_pages_and_every_style_is_named():
    style = (WEBUI / "js" / "style.js").read_text(encoding="utf-8")
    short = re.findall(r'"([a-z]+)"', re.search(r"SHORT = \[(.*?)\]", style).group(1))
    styles = re.findall(r'"([a-z]+)"', re.search(r"STYLES = \[(.*?)\]", style).group(1))
    ids = set()
    for f in (WEBUI / "js" / "modules").glob("*.js"):
        text = f.read_text(encoding="utf-8")
        ids |= set(re.findall(r'^\s*id: "([a-z]+)",', text, re.M))
        ids |= set(re.findall(r'export default page\("([a-z]+)"', text))
    assert len(short) == 6 and set(short) <= ids and {"today", "advanced"} <= ids
    for lang in ("it_IT", "en_US"):
        words = json.loads((WEBUI / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
        assert all(f"style.{s}" in words and f"style.{s}.hint" in words for s in styles)
        assert "Mac" not in " ".join(v for k, v in words.items() if k.startswith(("style.", "today.", "adv.")))


def test_the_server_takes_exactly_the_themes_and_styles_the_page_offers():
    """15 Oct: the colours, the style and the pins are each person's on the server; its lists are the page's."""
    import re
    js = (WEBUI / "js" / "theme.js").read_text(encoding="utf-8")
    style = (WEBUI / "js" / "style.js").read_text(encoding="utf-8")
    py = (WEBUI.parent / "aurora" / "api" / "users.py").read_text(encoding="utf-8")
    server = lambda key: re.findall(r'"([a-z]+)"', re.search(rf'"{key}": \((.*?)\)', py, re.S).group(1))   # noqa: E731
    assert server("theme") == re.findall(r'\{ id: "([a-z]+)"', js)
    assert server("style") == re.findall(r'"([a-z]+)"', re.search(r"STYLES = \[(.*?)\]", style).group(1))
