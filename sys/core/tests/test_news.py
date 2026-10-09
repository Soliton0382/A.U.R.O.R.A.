# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

spec = importlib.util.spec_from_file_location("news", Path(__file__).resolve().parents[2] / "plugins" / "news" / "server.py")
N = importlib.util.module_from_spec(spec)
spec.loader.exec_module(N)

# the stories are a day old whenever the suite runs (written with 2 Oct 2026, they fell out of «the last 168 hours» on
# 9 Oct at 10:00 GMT and the test failed with nothing changed)
DAY = (datetime.now(timezone.utc) - timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title>Nuova cometa &amp; altro</title><link>https://example.org/a</link><description>&lt;p&gt;Vista da &lt;b&gt;ESA&lt;/b&gt;&lt;/p&gt;</description><pubDate>%s</pubDate></item>
<item><title>Senza link valido</title><link>javascript:alert(1)</link></item>
</channel></rss>""" % DAY.strftime("%a, %d %b %Y %H:%M:%S GMT").encode()
ATOM = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Nuova cometa &amp; altro</title>
<link href="https://example.org/b"/><updated>%s</updated><summary>stessa notizia</summary></entry></feed>""" % (DAY + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ").encode()


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
