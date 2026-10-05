# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Knowledge by language and programming documentation (owner, 2026-10-05)."""
import io
import tarfile
from types import SimpleNamespace

from aurora import kno_docs, kno_sources


class Web:
    """A fake fetch: the answer chosen by the URL and the query."""
    def __init__(self, answers):
        self.answers, self.asked = answers, []           # [((url, {param: value} or None), answer)]

    def __call__(self, url, **params):
        self.asked.append((url, params))
        for (u, key), ans in self.answers:
            if url == u and all(params.get(k) == v for k, v in (key or {}).items()):
                return SimpleNamespace(json=lambda a=ans: a, text=ans if isinstance(ans, str) else "", content=ans if isinstance(ans, bytes) else b"")
        raise AssertionError(f"unexpected {url} {params}")


def test_the_installation_language_is_harvested_besides_english(cfg):
    cfg.values.update(AURORA_HARVEST_LANGS="", AURORA_LANG_DEFAULT="it_IT")
    assert kno_sources.langs(cfg) == ["en", "it"]
    cfg.values["AURORA_HARVEST_LANGS"] = "fr, it, xx"
    assert kno_sources.langs(cfg) == ["en", "fr", "it"]                  # an unknown language is ignored
    names = [n for n, s in kno_sources.specs(cfg, "history")]
    assert names[0] == "0" and "0.fr" in names and "0.it" in names     # Wikipedia again per language
    assert not any("." in n for n, s in kno_sources.specs(cfg, "physics"))   # no Wikipedia there: nothing more


def test_italian_wikipedia_follows_the_interlanguage_link(cfg):
    it_api = "https://it.wikipedia.org/w/api.php"
    web = Web([
        ((kno_sources.WIKI, {"prop": "langlinks", "titles": "Renaissance"}),
            {"query": {"pages": {"1": {"langlinks": [{"lang": "it", "*": "Rinascimento"}]}}}}),
        ((it_api, {"prop": "extracts", "titles": "Rinascimento"}),
            {"query": {"pages": {"2": {"title": "Rinascimento", "extract": "Il Rinascimento fu " + "un'epoca. " * 80
                                       + "\n== Note ==\nriferimenti"}}}}),
    ])
    st = {"titles": ["Renaissance"], "pos": 0}
    docs = kno_sources.wikipedia(web, cfg, "history", {"source": "wikipedia", "lang": "it"}, st, 5, False, set())
    assert [d.key for d in docs] == ["wikipedia:it:Rinascimento"] and docs[0].lang == "it"
    assert docs[0].url == "https://it.wikipedia.org/wiki/Rinascimento" and b"riferimenti" not in docs[0].data


def _archive():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:bz2") as tar:
        for name, text in (("python-3.14-docs-text/library/json.txt", "json — JSON encoder and decoder\n" + "*" * 30 + "\n" + "text " * 200),
                           ("python-3.14-docs-text/whatsnew/3.14.txt", "What's new\n" + "x " * 300)):
            data = text.encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def test_the_python_documentation_comes_from_its_text_archive(cfg):
    web = Web([((kno_docs.ARCHIVES, None), '<a href="python-3.14-docs-text.tar.bz2">'),
               ((kno_docs.ARCHIVES + "python-3.14-docs-text.tar.bz2", None), _archive())])
    st = {}
    docs = kno_docs.docs(web, cfg, "programming", {"source": "docs", "set": "python"}, st, 10, True, set())
    assert [d.key for d in docs] == ["docs:python:library/json.txt"]    # the library, not the what's-new pages
    assert docs[0].title == "Python 3.14: json — JSON encoder and decoder" and docs[0].licence == "PSF-2.0"
    assert docs[0].url == "https://docs.python.org/3.14/library/json.html" and st["done"]


def test_mdn_pages_lose_their_front_matter_and_macros(cfg):
    page = "---\ntitle: Array.prototype.map()\nslug: x\n---\n{{JSRef}}\nThe **map()** method creates " + "a new array. " * 60
    title, text = kno_docs.clean_markdown(page)
    assert title == "Array.prototype.map()" and "{{" not in text and not text.startswith("---")
    spec = {"source": "docs", "set": "github", "repo": "mdn/content", "branch": "main", "prefix": "files/en-us/web/javascript/",
            "suffix": "/index.md", "licence": "CC-BY-SA-2.5", "label": "MDN JavaScript",
            "url": "https://developer.mozilla.org/en-US/docs/Web/JavaScript/{path}"}
    path = "files/en-us/web/javascript/reference/global_objects/array/map/index.md"
    web = Web([(("https://api.github.com/repos/mdn/content/git/trees/main", None), {"tree": [{"type": "blob", "path": path}]}),
               ((f"https://raw.githubusercontent.com/mdn/content/main/{path}", None), page)])
    docs = kno_docs.docs(web, cfg, "programming", spec, {}, 5, True, set())
    assert docs[0].url == "https://developer.mozilla.org/en-US/docs/Web/JavaScript/reference/global_objects/array/map"
    assert docs[0].title == "MDN JavaScript: Array.prototype.map()"
