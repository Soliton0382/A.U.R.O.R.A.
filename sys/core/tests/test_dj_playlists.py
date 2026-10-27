# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The player's playlists (aud_playlists, 28 Oct): saved whole and checked (a name, track refs only, each once, an id
kept or made), a deleted track leaves every list when read, the file the user's alone. The page's folders were tried
in the running API (GET /v1/aurora/dj carries them, PUT /v1/aurora/dj/playlists saves them)."""
import os

import pytest

from aurora import aud_playlists as P


def test_lists_checked_saved_and_pruned(tmp_path):
    out = P.save(tmp_path, [{"name": "  Trance   cosmica ", "items": ["mixes/viaggio-20261028-1700.mp3", "mio.mp3", "mio.mp3"]},
                            {"id": "zzz", "name": "Metal", "items": []}])
    assert out[0]["name"] == "Trance cosmica" and out[0]["items"] == ["mixes/viaggio-20261028-1700.mp3", "mio.mp3"]
    assert all(P.ID.fullmatch(p["id"]) for p in out) and out[0]["id"] != out[1]["id"]
    assert oct(os.stat(tmp_path / P.FILE).st_mode & 0o777) == "0o600"
    kept = P.save(tmp_path, out)                                                       # the ids stay
    assert [p["id"] for p in kept] == [p["id"] for p in out]
    assert P.load(tmp_path, {"mio.mp3"})[0]["items"] == ["mio.mp3"]                     # the mix was deleted
    for bad in ([{"name": "", "items": []}], [{"name": "x", "items": ["../../etc/passwd"]}], [{"name": "x", "items": ["a.exe"]}], "x"):
        with pytest.raises(ValueError):
            P.check(bad)
    assert P.load(tmp_path / "none") == []
