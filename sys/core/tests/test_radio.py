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
