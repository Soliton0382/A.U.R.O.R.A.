# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔭 The guiding followed live (ROADMAP N28): a guider that speaks PHD2's event protocol (one JSON a line, JSON-RPC
on the same connection) on this machine, its steps read in arcseconds, the RMS computed, the events kept; nothing is
ever sent that would change the guider."""
import json
import math
import socket
import threading
import time

from aurora import ast_phd2


def fake_guider(steps: list[tuple[float, float]], scale: float = 2.0):
    """A guider on a free port: says its version, answers the read-only questions, then sends the steps and a lost
    star; returns (port, what it received)."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    got: list[dict] = []

    def serve():
        conn, _ = srv.accept()
        f = conn.makefile("rwb")
        f.write(b'{"Event":"Version","PHDVersion":"2.6.14","Host":"TEST","Inst":1,"MsgVersion":1}\r\n')
        f.flush()
        conn.settimeout(2)
        for _ in range(2):                                  # get_pixel_scale, get_app_state
            q = json.loads(f.readline())
            got.append(q)
            r = scale if q["method"] == "get_pixel_scale" else "Guiding"
            f.write((json.dumps({"jsonrpc": "2.0", "result": r, "id": q["id"]}) + "\r\n").encode())
            f.flush()
        for i, (ra, dec) in enumerate(steps):
            f.write((json.dumps({"Event": "GuideStep", "Timestamp": 1000 + i, "Frame": i, "RADistanceRaw": ra,
                                 "DECDistanceRaw": dec, "RADuration": 120, "RADirection": "East", "DECDuration": 0,
                                 "DECDirection": "North", "SNR": 40.0}) + "\r\n").encode())
        f.write(b'{"Event":"StarLost","Timestamp":2000,"Status":-1,"Error":"star lost"}\r\n')
        f.flush()
        time.sleep(1.5)
        conn.close()
        srv.close()

    threading.Thread(target=serve, daemon=True).start()
    return srv.getsockname()[1], got


def test_the_steps_become_arcseconds_and_rms_and_only_questions_are_sent():
    steps = [(0.5, -0.25), (-0.5, 0.25), (0.5, -0.25), (-0.5, 0.25)]
    port, got = fake_guider(steps, scale=2.0)
    deadline = time.time() + 5
    snap = ast_phd2.watch("127.0.0.1", port)
    while time.time() < deadline and not (len(snap["steps"]) == 4 and snap["events"]):
        time.sleep(0.1)
        snap = ast_phd2.watch("127.0.0.1", port)
    assert snap["version"] == "2.6.14" and snap["scale"] == 2.0
    assert [s["ra"] for s in snap["steps"]] == [1.0, -1.0, 1.0, -1.0]                 # pixels × 2″/px
    assert snap["rms"]["ra"] == 1.0 and snap["rms"]["dec"] == 0.5 and snap["rms"]["total"] == round(math.hypot(1, .5), 3)
    assert snap["steps"][0]["ra_ms"] == -120                                              # East: the other way
    assert snap["events"][-1]["event"] == "StarLost" and snap["state"] == "LostLock"
    assert {q["method"] for q in got} == {"get_pixel_scale", "get_app_state"}            # read-only questions only


def test_no_guider_is_said_not_raised():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()                                                                            # nobody listens there
    snap = ast_phd2.watch("127.0.0.1", port)
    for _ in range(30):
        if snap["error"]:
            break
        time.sleep(0.1)
        snap = ast_phd2.watch("127.0.0.1", port)
    assert not snap["connected"] and snap["error"] and snap["steps"] == []
