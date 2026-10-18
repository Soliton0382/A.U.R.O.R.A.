# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The camera turned by hand to the framing's angle (owner, 19 Oct: no rotator): never more than 90° (θ and θ + 180°
frame the same), the way of turning learned from the first turn and kept, a mirrored solve apart, done within the
tolerance; N.I.N.A.'s capture answer read. Invented angles and a fake N.I.N.A."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from aurora import ast_rotate as R


def solved(pa, flipped=False):
    return {"pa": pa, "flipped": flipped}


def test_a_rectangle_never_turns_more_than_90_degrees():
    assert R.wrap90(170) == -10 and R.wrap90(-100) == 80 and R.wrap90(90) == -90 and R.wrap90(0.5) == 0.5
    out, _ = R.step(solved(10.0), 185.0, {})
    assert out["turn"] == -5.0                               # 185° is 5°, not 175° the other way


def test_the_first_turn_teaches_which_way_raises_the_angle():
    out, state = R.step(solved(100.0), 110.0, {}, now=1000)
    assert out["told"] == "cw" and not out["sure"] and "prima volta" in out["say"]
    out, state = R.step(solved(96.0), 110.0, state, now=1060)           # turned clockwise: the angle went down
    assert state["cw_raises"] == {"n": False} and "sceso di 4.0" in out["learned"]
    assert out["told"] == "ccw" and out["sure"] and "14.0° in senso antiorario" in out["say"]
    out, state = R.step(solved(109.8), 110.0, state, now=1120)
    assert out["done"] and state == {"cw_raises": {"n": False}, "last": {}}


def test_what_was_learned_stays_and_a_mirrored_solve_is_apart():
    known = {"cw_raises": {"n": True}, "last": {}}
    out, _ = R.step(solved(50.0), 40.0, known)
    assert out["told"] == "ccw" and out["sure"]
    out, _ = R.step(solved(50.0, flipped=True), 40.0, known)
    assert out["told"] == "cw" and not out["sure"]


def test_an_old_or_too_small_turn_teaches_nothing():
    state = {"last": {"pa": 100.0, "at": 0, "told": "cw", "parity": "n"}}
    out, s = R.step(solved(90.0), 110.0, state, now=R.LEARN_S + 10)
    assert "learned" not in out and s["cw_raises"] == {}
    state["last"]["at"] = 100
    out, s = R.step(solved(100.1), 110.0, state, now=150)
    assert "learned" not in out


class Nina(BaseHTTPRequestHandler):
    reply = {}

    def do_GET(self):  # noqa: N802
        body = json.dumps(Nina.reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)
        Nina.path_seen = self.path

    def log_message(self, *a):
        pass


def test_ninas_capture_answer_is_read():
    srv = HTTPServer(("127.0.0.1", 0), Nina)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        port = srv.server_address[1]
        Nina.reply = {"Success": True, "Response": {"PlateSolveResult": {
            "Success": True, "PositionAngle": 37.5, "Flipped": False, "PixelScale": 1.26,
            "Coordinates": {"RADegrees": 83.8, "DECDegrees": -5.4}}}}
        got = R.capture("127.0.0.1", port, timeout=5)
        assert got == {"pa": 37.5, "flipped": False, "ra_deg": 83.8, "dec_deg": -5.4, "scale": 1.26}
        assert "solve=true" in Nina.path_seen and "omitImage=true" in Nina.path_seen
        Nina.reply = {"Success": True, "Response": {"PlateSolveResult": {"Success": False}}}
        assert "plate solving" in R.capture("127.0.0.1", port, timeout=5)["error"]
        Nina.reply = {"Success": False, "Error": "Camera currently exposing"}
        assert R.capture("127.0.0.1", port, timeout=5)["error"] == "Camera currently exposing"
    finally:
        srv.shutdown()
    assert "non risponde" in R.capture("127.0.0.1", 9, timeout=1)["error"]
