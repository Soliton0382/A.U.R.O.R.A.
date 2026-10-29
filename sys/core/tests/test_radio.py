# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📻 Internet radio (aud_radio, 28 Oct): the directory asked through net_public (public addresses only), a stream's
address looked up by the station's id and never taken from the page, a bad id refused, the stations kept per user
(0600), only https icons. The directory is a stand-in; the live trial is in ROADMAP N61."""
import os

import pytest

from aurora import aud_radio as R

SID = "960e57c5-0601-11e8-ae97-52543be04c81"


@pytest.fixture
def directory(monkeypatch):
    asked = []

    class Resp:
        def __init__(self, data):
            self.data = data

        def raise_for_status(self):
            return self

        def json(self):
            return self.data

    def request(method, url, **kw):
        asked.append(url)
        if "/byuuid/" in url:
            return Resp([{"stationuuid": SID, "name": "Cosmo", "url_resolved": "https://stream.example.org/live.mp3"}])
        return Resp([{"stationuuid": SID, "name": "Cosmo FM", "tags": "trance,vocal trance", "codec": "MP3",
                      "bitrate": 192, "favicon": "http://insecure.example/icon.png"}])
    monkeypatch.setattr(R.net_public, "request", request)
    R._cache.clear()
    return asked


def test_search_and_a_stream_looked_up_by_id(directory):
    s = R.search(tag="vocal trance")
    assert s[0]["id"] == SID and s[0]["favicon"] == "" and "tag=vocal+trance" in directory[0]
    assert R.stream_url(SID) == ("https://stream.example.org/live.mp3", "Cosmo")
    for bad in ("../../etc", "https://evil.example/x.mp3", ""):
        with pytest.raises(ValueError):
            R.stream_url(bad)
    R.search(tag="vocal trance")
    assert len(directory) == 2                                                     # the same search: from memory


def test_the_stations_kept_are_the_user_s(tmp_path):
    R.keep(tmp_path, {"id": SID, "name": "Cosmo FM", "tags": "trance"}, True)
    assert [s["name"] for s in R.favourites(tmp_path)] == ["Cosmo FM"]
    assert oct(os.stat(tmp_path / "radio.json").st_mode & 0o777) == "0o600"
    assert R.keep(tmp_path, {"id": SID}, False) == []
    with pytest.raises(ValueError):
        R.keep(tmp_path, {"id": "x"}, True)


def test_every_genre_family_comes_with_its_stations_and_the_empty_ones_go(monkeypatch):
    from aurora import aud_radio
    tags = [{"name": "house", "stationcount": 793}, {"name": "goa", "stationcount": 2}, {"name": "shoegaze", "stationcount": 40}]
    monkeypatch.setattr(aud_radio, "_get", lambda path: tags)
    g = aud_radio.genres()
    shown = {x["tag"]: x["stations"] for f in g["families"] for x in f["genres"]}
    assert shown == {"house": 793} and g["more"] == ["shoegaze"]          # goa has too few; shoegaze is not curated

    def down(path):
        raise RuntimeError("the radio directory did not answer")
    monkeypatch.setattr(aud_radio, "_get", down)
    assert sum(len(f["genres"]) for f in aud_radio.genres()["families"]) == sum(len(i) for _, i in aud_radio.GENRES)


def test_a_genre_is_the_whole_tag_and_its_own_stations_come_first(monkeypatch):
    asked = []

    def get(path):
        asked.append(path)
        return [{"stationuuid": "a" * 36, "name": "Every genre", "tags": "pop,rock,news,talk,jazz,dance,trance"},
                {"stationuuid": "b" * 36, "name": "Trance only", "tags": "trance,vocal trance"}]
    monkeypatch.setattr(R, "_get", get)
    found = R.search(tag="trance", limit=40)
    assert "tagExact=true" in asked[0] and "limit=80" in asked[0]
    assert [s["name"] for s in found] == ["Trance only", "Every genre"]
    R.search(name="cosmo")
    assert "tagExact" not in asked[1] and "limit=40" in asked[1]


def test_a_third_radio_closes_the_oldest_never_refused(monkeypatch):
    import asyncio

    from aurora.sys_config import ConfigError
    try:
        from aurora.api import radio as A
    except ConfigError:                                   # the API loads the configuration: none here (publish's run)
        pytest.skip("no configuration to load the API with")

    class Stream:
        status_code, headers = 200, {"content-type": "audio/mpeg"}

        def __init__(self):
            self.closed = False

        def iter_raw(self, n):
            yield b"x" * 8

        def close(self):
            self.closed = True

    opened = []

    def open_stream(*a, **k):
        opened.append(Stream())
        return Stream(), opened[-1]
    monkeypatch.setattr(R, "stream_url", lambda sid: ("https://stream.example.org/live.mp3", "Cosmo"))
    monkeypatch.setattr(A, "me", lambda: "ada")
    monkeypatch.setattr("aurora.net_public.open_stream", open_stream)
    A._streams.clear()

    async def three():
        replies = [await A.radio_stream(SID) for _ in range(3)]
        assert opened[0].closed and not opened[1].closed and not opened[2].closed
        assert len(A._streams["ada"]) == 2
        async for _ in replies[2].body_iterator:          # played to its end: its place given back
            pass
        assert opened[2] not in A._streams["ada"]
    asyncio.run(three())
