# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔭 The guiding followed live (ROADMAP N28; owner, 16 Oct: «grafici stile PHD2… quello che sta facendo Aurora per
risolvere i problemi di inseguimento»): PHD2's own event server on the telescope's PC (TCP, port 4400 by default: one
JSON event a line — GuideStep, StarLost, Settle…, and JSON-RPC calls on the same connection). Read only here: the
events, the pixel scale and the app's state (get_pixel_scale, get_app_state); nothing is ever sent that changes PHD2
(the tuner that may, when the person turns it on, is ast_autoguide, on its own connection).

One watcher per host, started by whoever asks for the picture and stopped by itself when nobody has asked for
IDLE_S: a night's guiding is not followed when nobody looks (the routines that watch a night ask for it themselves).
The picture: the last STEPS guide steps (RA and DEC error in arcseconds, the corrections), the RMS of RA, DEC and
total over them, the star's SNR, the events that matter (star lost, settling, calibration, dither), the state."""
from __future__ import annotations

import json
import math
import socket
import threading
import time
from collections import deque

STEPS = 600                    # about 10-20 minutes of 1-2 s guide exposures
EVENTS = 80
IDLE_S = 300.0
PORT = 4400
KEPT = ("StarLost", "LockPositionLost", "Settling", "SettleDone", "StartCalibration", "CalibrationComplete",
        "CalibrationFailed", "GuidingDithered", "Paused", "Resumed", "GuidingStopped", "StartGuiding", "LoopingExposures",
        "Alert", "ConfigurationChange", "GuideParamChange")


class Watcher:
    """The connection to one PHD2 and what it said; thread-safe snapshot()."""

    def __init__(self, host: str, port: int = PORT):
        self.host, self.port = host, int(port)
        self.lock = threading.Lock()
        self.steps: deque = deque(maxlen=STEPS)
        self.events: deque = deque(maxlen=EVENTS)
        self.state, self.version, self.scale, self.error = "", "", None, ""
        self.connected, self.asked = False, time.time()
        self.stop = threading.Event()
        self._id = 0
        self.thread = threading.Thread(target=self._run, name=f"phd2-{host}", daemon=True)
        self.thread.start()

    # ---- the connection ---------------------------------------------------------------------------------------
    def _send(self, sock: socket.socket, method: str) -> None:
        self._id += 1
        sock.sendall((json.dumps({"method": method, "id": self._id}) + "\r\n").encode())

    def _run(self) -> None:
        while not self.stop.is_set() and time.time() - self.asked < IDLE_S:
            try:
                with socket.create_connection((self.host, self.port), timeout=5) as sock:
                    sock.settimeout(2)
                    with self.lock:
                        self.connected, self.error = True, ""
                    for m in ("get_pixel_scale", "get_app_state"):     # read-only questions
                        self._send(sock, m)
                    buf = b""
                    while not self.stop.is_set() and time.time() - self.asked < IDLE_S:
                        try:
                            chunk = sock.recv(65536)
                        except socket.timeout:
                            continue
                        if not chunk:
                            raise ConnectionError("PHD2 closed the connection")
                        buf += chunk
                        while b"\n" in buf:
                            line, buf = buf.split(b"\n", 1)
                            if line.strip():
                                self.take(json.loads(line.decode("utf-8", "replace")))
            except (OSError, ValueError, ConnectionError) as e:
                with self.lock:
                    self.connected, self.error = False, str(e)[:200]
                self.stop.wait(5)                     # PHD2 closed or not there yet: again in a moment
        with self.lock:
            self.connected = False

    # ---- one message ------------------------------------------------------------------------------------------
    def take(self, m: dict) -> None:
        """One line of PHD2: an event, or the answer to one of our questions."""
        with self.lock:
            if "jsonrpc" in m:
                r = m.get("result")
                if isinstance(r, (int, float)) and not isinstance(r, bool):
                    self.scale = float(r)
                elif isinstance(r, str):
                    self.state = r
                return
            ev = m.get("Event", "")
            if ev == "Version":
                self.version = str(m.get("PHDVersion", ""))
            elif ev == "AppState":
                self.state = str(m.get("State", ""))
            elif ev == "GuideStep":
                s = self.scale or 1.0
                self.state = "Guiding"
                self.steps.append({"t": m.get("Timestamp") or time.time(), "frame": m.get("Frame"),
                                   "ra": round(float(m.get("RADistanceRaw") or 0) * s, 3),
                                   "dec": round(float(m.get("DECDistanceRaw") or 0) * s, 3),
                                   "ra_ms": int(m.get("RADuration") or 0) * (1 if m.get("RADirection") in ("West", None) else -1),
                                   "dec_ms": int(m.get("DECDuration") or 0) * (1 if m.get("DECDirection") in ("North", None) else -1),
                                   "snr": m.get("SNR"), "hfd": m.get("HFD"), "arcsec": self.scale is not None})
            if ev in KEPT:
                self.events.append({"t": m.get("Timestamp") or time.time(), "event": ev,
                                    **{k: m[k] for k in ("Status", "Msg", "Error", "Type", "Name", "Value") if k in m}})
                if ev in ("Paused", "GuidingStopped", "LoopingExposures", "StarLost"):
                    self.state = {"Paused": "Paused", "GuidingStopped": "Stopped", "LoopingExposures": "Looping",
                                  "StarLost": "LostLock"}[ev]

    def snapshot(self) -> dict:
        self.asked = time.time()
        with self.lock:
            steps = list(self.steps)
            out = {"host": self.host, "port": self.port, "connected": self.connected, "error": self.error,
                   "state": self.state, "version": self.version, "scale": self.scale, "steps": steps,
                   "events": list(self.events)[-20:], "rms": rms(steps)}
        return out


def rms(steps: list[dict], last: int = 120) -> dict:
    """The RMS of RA, DEC and total over the last steps (arcseconds when the scale is known), PHD2's way."""
    s = steps[-last:]
    if not s:
        return {"ra": None, "dec": None, "total": None, "n": 0}
    def r(k):
        mean = sum(x[k] for x in s) / len(s)
        return math.sqrt(sum((x[k] - mean) ** 2 for x in s) / len(s))
    ra, dec = r("ra"), r("dec")
    return {"ra": round(ra, 3), "dec": round(dec, 3), "total": round(math.hypot(ra, dec), 3), "n": len(s),
            "peak_ra": round(max(abs(x["ra"]) for x in s), 3), "peak_dec": round(max(abs(x["dec"]) for x in s), 3)}


_watchers: dict[tuple[str, int], Watcher] = {}
_lock = threading.Lock()


def watch(host: str, port: int = PORT) -> dict:
    """The picture of the PHD2 at host:port, starting its watcher when none runs."""
    key = (host, int(port))
    with _lock:
        w = _watchers.get(key)
        if w is None or not w.thread.is_alive():
            w = _watchers[key] = Watcher(host, port)
    return w.snapshot()
