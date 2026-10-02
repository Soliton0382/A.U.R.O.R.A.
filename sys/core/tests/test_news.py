# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("news", Path(__file__).resolve().parents[2] / "plugins" / "news" / "server.py")
N = importlib.util.module_from_spec(spec)
spec.loader.exec_module(N)

RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title>Nuova cometa &amp; altro</title><link>https://example.org/a</link><description>&lt;p&gt;Vista da &lt;b&gt;ESA&lt;/b&gt;&lt;/p&gt;</description><pubDate>Fri, 02 Oct 2026 10:00:00 GMT</pubDate></item>
<item><title>Senza link valido</title><link>javascript:alert(1)</link></item>
</channel></rss>"""
ATOM = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Nuova cometa &amp; altro</title>
<link href="https://example.org/b"/><updated>2026-10-02T11:00:00Z</updated><summary>stessa notizia</summary></entry></feed>"""


class R:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        return self


def test_rss_and_atom_are_read_cleaned_and_a_story_counted_once(monkeypatch):
    pages = {"https://f/rss": RSS, "https://f/atom": ATOM}
    monkeypatch.setattr(N.httpx, "get", lambda url, **k: R(pages[url]))
    items = N._read("Uno", "https://f/rss")
    assert [i["title"] for i in items] == ["Nuova cometa & altro"]             # the javascript: link dropped
    assert items[0]["summary"] == "Vista da ESA" and items[0]["when"].hour == 10
    monkeypatch.setattr(N, "FEEDS", {"scienza": [["Uno", "https://f/rss"], ["Due", "https://f/atom"]]})
    out = N.news_headlines("scienza", hours=168)
    assert out.count("Nuova cometa") == 1 and "Due" in out                     # the newest copy, once
