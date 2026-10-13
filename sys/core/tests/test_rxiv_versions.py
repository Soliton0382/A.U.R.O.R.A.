# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A preprint's versions are one document: the latest of each DOI on a page (two versions, retitled, came as two)."""
from aurora import kno_sources as S


class R:
    def __init__(self, data=None, content=b""):
        self._d, self.content = data, content

    def json(self):
        return self._d


def test_only_the_latest_version_of_a_doi_is_taken(monkeypatch):
    page = {"messages": [{"total": 3}], "collection": [
        {"doi": "10.1/a", "version": "1", "title": "Old title", "jatsxml": "v1"},
        {"doi": "10.1/a", "version": "2", "title": "New title", "jatsxml": "v2"},
        {"doi": "10.1/b", "version": "1", "title": "Other", "jatsxml": "b1"}]}
    monkeypatch.setattr(S, "jats_text", lambda content: (content.decode(), "text " * 200))
    fetch = lambda url, **kw: R(page) if "api.biorxiv.org" in url else R(content=url.encode())
    docs = S.rxiv("biorxiv")(fetch, None, "biomedicine", {}, {}, 10, False, set())
    assert sorted(d.title for d in docs) == ["b1", "v2"]
