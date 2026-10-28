# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🟢 Spotify (28 Oct): the WebUI's security policy opens to Spotify's player only while a Client ID is set, and only
to its script, frame, sign-in, API and pictures; the plugin says whether it is set up."""
from aurora import net_https


def test_the_policy_opens_to_spotify_only_when_set_up(cfg):
    cfg.values["AURORA_SPOTIFY_CLIENT_ID"] = ""
    assert net_https.csp(cfg) == net_https.CSP and "spotify" not in net_https.CSP and "scdn" not in net_https.CSP
    cfg.values["AURORA_SPOTIFY_CLIENT_ID"] = "0123456789abcdef"
    on = {p.split()[0]: p for p in net_https.csp(cfg).split("; ")}
    assert "https://sdk.scdn.co" in on["script-src"] and "https://sdk.scdn.co" in on["frame-src"]
    assert "https://accounts.spotify.com" in on["connect-src"] and "https://api.spotify.com" in on["connect-src"]
    assert on["default-src"] == "default-src 'self'" and "frame-ancestors 'none'" in on.values()   # the rest unchanged
