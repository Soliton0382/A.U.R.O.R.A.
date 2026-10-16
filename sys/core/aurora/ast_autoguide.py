# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔭 The guiding tuned during the night (ROADMAP N28; owner, 16 Oct: «lei deve poterli leggere in real time per procedere
con la correzione automatizzata della guida per migliorarla durante la sessione»): PHD2's guide steps followed live
(ast_phd2's watcher) and, when the person turns it on, one parameter changed at a time inside the limits they set —
the guide exposure, the RA and DEC minimum move — each change tried A/B on the RMS and put back when it made things
worse. Three modes: off (the default), propose (said, never sent), apply.

What is never done: a change while PHD2 is not guiding, settling, or right after a dither or a lost star; a value outside
the person's limits; a second change before the first has been judged; anything but those three parameters (the
calibration, the algorithms, the mount are left alone). Every proposal, change, keep and revert is written to
autoguide.jsonl in the person's astro folder.

The reading (diagnose) is a pure function: a window of clean steps and the events → at most one proposal, with why:
  the star lost or a low SNR → a longer exposure; corrections that flip sign most of the time with a sizeable error
  (chasing the seeing) → a larger minimum move; an error that stays on one side (under-correcting) → a smaller one."""
from __future__ import annotations

import json
import math
import socket
import statistics
import threading
import time
from pathlib import Path

from aurora import ast_phd2

MODES = ("off", "propose", "apply")
EXPOSURES = (500, 1000, 1500, 2000, 2500, 3000, 3500, 4000)
WINDOW = 180                  # clean steps to read before a proposal (3–6 min at 1–2 s): the seeing changes by the
                              # minute, a short look tunes on chance («attratti dal casuale», B. Waddington)
TRIAL = 240                   # clean steps to judge a change: the RMS of n steps scatters by ~1/√(2n), 4.6 % here
QUIET_S = 20.0                # after a settle, a dither, a lost star: these seconds do not count
COOLDOWN_S = 600.0            # between two changes: few and small, as PHD2's author advises
WORSE = 1.15                  # put back when the total RMS gets 15 % worse: ~3 × that scatter, not noise
STEP_MOVE = 0.05


def defaults(advice_rows: list[dict] | None = None) -> dict:
    """The limits: from the values advised when there are (the Guiding Assistant's ranges), else PHD2's usual ones."""
    r = {x["key"]: x for x in advice_rows or []}
    lim = {"exposure_ms": [1000, 3000], "ra_min_move": [0.10, 0.40], "dec_min_move": [0.10, 0.50]}
    adv = str((r.get("guide_exposure") or {}).get("advised") or "")
    if "–" in adv:
        a, b = (float(x) for x in adv.split("–"))
        lim["exposure_ms"] = [int(a * 1000), int(b * 1000)]
    for k, key in (("ra_min_move", "min_move_ra"), ("dec_min_move", "min_move_dec")):
        v = (r.get(key) or {}).get("advised")
        if isinstance(v, (int, float)):
            lim[k] = [round(v * 0.6, 2), round(v * 1.6, 2)]
    return lim


# ---- PHD2's JSON-RPC, on its own short connection ---------------------------------------------------------------------
def rpc(host: str, port: int, method: str, params: list | None = None, timeout: float = 5.0):
    """One call to PHD2 (the events that arrive on the same connection are skipped); its result, or RuntimeError."""
    with socket.create_connection((host, port), timeout=timeout) as s:
        s.settimeout(timeout)
        msg = {"method": method, "id": 1}
        if params is not None:
            msg["params"] = params
        s.sendall((json.dumps(msg) + "\r\n").encode())
        buf, end = b"", time.time() + timeout
        while time.time() < end:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                try:
                    m = json.loads(line)
                except ValueError:
                    continue
                if m.get("jsonrpc") and m.get("id") == 1:
                    if "error" in m:
                        raise RuntimeError(str(m["error"].get("message", m["error"]))[:200])
                    return m.get("result")
    raise RuntimeError(f"PHD2 did not answer {method}")


def _norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


class Phd2Params:
    """The three parameters as PHD2 names them (asked once: the names depend on the algorithm in use)."""

    def __init__(self, host: str, port: int, call=rpc):
        self.host, self.port, self.call = host, port, call
        self.names: dict[str, str] = {}

    def _name(self, axis: str) -> str:
        if axis not in self.names:
            names = self.call(self.host, self.port, "get_algo_param_names", [axis]) or []
            self.names[axis] = next((n for n in names if _norm(n) == "minmove"), "")
            if not self.names[axis]:
                raise RuntimeError(f"no minimum move on {axis}: {names}")
        return self.names[axis]

    def get(self) -> dict:
        return {"exposure_ms": int(self.call(self.host, self.port, "get_exposure")),
                "ra_min_move": float(self.call(self.host, self.port, "get_algo_param", ["ra", self._name("ra")])),
                "dec_min_move": float(self.call(self.host, self.port, "get_algo_param", ["dec", self._name("dec")]))}

    def set(self, param: str, value) -> None:
        if param == "exposure_ms":
            self.call(self.host, self.port, "set_exposure", [int(value)])
        else:
            axis = "ra" if param.startswith("ra") else "dec"
            self.call(self.host, self.port, "set_algo_param", [axis, self._name(axis), float(value)])


# ---- the reading ------------------------------------------------------------------------------------------------------
def clean(steps: list[dict], events: list[dict]) -> list[dict]:
    """The steps that count: none within QUIET_S after a settle, a dither, a lost star, a calibration."""
    marks = [e["t"] for e in events if e.get("event") in ("Settling", "SettleDone", "GuidingDithered", "StarLost",
                                                         "LockPositionLost", "StartGuiding", "CalibrationComplete")]
    return [s for s in steps if not any(0 <= s["t"] - m < QUIET_S for m in marks)]


def _rms(v: list[float]) -> float:
    if not v:
        return 0.0
    m = sum(v) / len(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / len(v))


def total_rms(steps: list[dict]) -> float:
    return round(math.hypot(_rms([s["ra"] for s in steps]), _rms([s["dec"] for s in steps])), 3)


def _flips(ms: list[int]) -> float:
    """Of the consecutive corrections that both moved, the share that went the other way."""
    moved = [x for x in ms if x]
    pairs = list(zip(moved, moved[1:]))
    return sum(1 for a, b in pairs if (a > 0) != (b > 0)) / len(pairs) if len(pairs) >= 10 else 0.0


def _next(values: tuple, now: int, up: bool):
    seq = [v for v in values if (v > now if up else v < now)]
    return (min(seq) if up else max(seq)) if seq else None


def diagnose(steps: list[dict], events: list[dict], now: dict, limits: dict, tried: set | None = None) -> dict | None:
    """At most one proposal {param, from, to, why, numbers}, or None. steps: the clean window, in arcseconds."""
    tried = tried or set()
    if len(steps) < WINDOW:
        return None
    w = steps[-WINDOW:]
    lost = sum(1 for e in events if e.get("event") == "StarLost" and e["t"] >= w[0]["t"])
    snr = statistics.median(s["snr"] for s in w if s.get("snr") is not None) if any(s.get("snr") for s in w) else None

    def ok(param, to):
        lo, hi = limits[param]
        return to is not None and lo - 1e-9 <= to <= hi + 1e-9 and (param, to) not in tried and to != now[param]

    if lost >= 2 or (snr is not None and snr < 12):
        to = _next(EXPOSURES, now["exposure_ms"], True)
        if ok("exposure_ms", to):
            return {"param": "exposure_ms", "from": now["exposure_ms"], "to": to, "why": "star_weak", "lost": lost, "snr": snr}
    for axis in ("ra", "dec"):
        err = [s[axis] for s in w]
        r, mean = _rms(err), sum(err) / len(err)
        flips = _flips([s[f"{axis}_ms"] for s in w])
        p = f"{axis}_min_move"
        if flips > 0.6 and r > 0.3:                                   # corrections chasing the seeing
            to = round(now[p] + STEP_MOVE, 2)
            if ok(p, to):
                return {"param": p, "from": now[p], "to": to, "why": "chasing", "flips": round(flips, 2), "rms": round(r, 2)}
        off = math.sqrt(sum(x * x for x in err) / len(err))           # the distance from the lock, offset included
        if off > 0.3 and abs(mean) > 0.5 * off and flips < 0.4:       # the error stays on one side
            to = round(now[p] - STEP_MOVE, 2)
            if ok(p, to):
                return {"param": p, "from": now[p], "to": to, "why": "lagging", "mean": round(mean, 2), "rms": round(off, 2)}
    return None


# ---- the loop ---------------------------------------------------------------------------------------------------------
class Tuner:
    """One per person and telescope PC: reads the watcher's picture every few seconds and acts as the mode says."""

    def __init__(self, host: str, port: int, folder: Path, mode: str, limits: dict, params: Phd2Params | None = None):
        self.host, self.port, self.folder = host, port, folder
        self.mode, self.limits = mode, limits
        self.params = params or Phd2Params(host, port)
        self.trial: dict | None = None
        self.last_change = 0.0
        self.tried: dict[tuple, float] = {}
        self.proposal: dict | None = None
        self.now: dict = {}
        self.error = ""
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, name=f"autoguide-{host}", daemon=True)
        self.thread.start()

    def write(self, action: str, **what) -> None:
        line = {"t": round(time.time(), 1), "action": action, "mode": self.mode, **what}
        try:
            with (self.folder / "autoguide.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def _run(self) -> None:
        while not self.stop.wait(10) and self.mode != "off":
            try:
                self.step(ast_phd2.watch(self.host, self.port))
                self.error = ""
            except (OSError, RuntimeError, ValueError, TypeError) as e:
                self.error = str(e)[:200]

    def step(self, snap: dict, clock=time.time) -> None:
        """One look: judge a running trial, or read the window and propose / apply one change."""
        if snap.get("state") != "Guiding" or not snap.get("connected", True):
            return
        steps = clean(snap["steps"], snap["events"])
        t = clock()
        self.tried = {k: v for k, v in self.tried.items() if t - v < 1800}
        if self.trial:
            after = [s for s in steps if s["t"] > self.trial["t"]]
            if len(after) < TRIAL:
                return
            rms = total_rms(after[-TRIAL:])
            tr, self.trial = self.trial, None
            if rms > tr["before"] * WORSE:
                self.params.set(tr["param"], tr["from"])
                self.tried[(tr["param"], tr["to"])] = t
                self.write("revert", param=tr["param"], to=tr["from"], rms_before=tr["before"], rms_after=rms)
            else:
                self.write("keep", param=tr["param"], value=tr["to"], rms_before=tr["before"], rms_after=rms)
            self.last_change = t
            return
        if t - self.last_change < COOLDOWN_S:
            return
        self.now = self.params.get()
        p = diagnose(steps, snap["events"], self.now, self.limits, set(self.tried))
        if p != self.proposal and p:
            self.write("propose", **p)
        self.proposal = p
        if p and self.mode == "apply":
            before = total_rms(steps[-WINDOW:])
            self.params.set(p["param"], p["to"])
            self.trial = {**p, "before": before, "t": max(s["t"] for s in steps)}
            self.last_change = t
            self.proposal = None
            self.write("apply", **p, rms_before=before)

    def state(self) -> dict:
        return {"mode": self.mode, "limits": self.limits, "running": self.thread.is_alive(), "now": self.now,
                "proposal": self.proposal, "trial": self.trial, "error": self.error}


_tuners: dict[str, Tuner] = {}
_lock = threading.Lock()


def ensure(who: str, host: str, port: int, folder: Path, mode: str, limits: dict) -> Tuner | None:
    """The person's tuner as the setup says: started, changed, or stopped (mode off)."""
    with _lock:
        t = _tuners.get(who)
        if mode not in MODES or mode == "off" or not host:
            if t:
                t.mode = "off"
                t.stop.set()
                _tuners.pop(who, None)
            return None
        if t and t.thread.is_alive() and (t.host, t.port) == (host, port):
            t.mode, t.limits = mode, limits
            return t
        if t:
            t.stop.set()
        t = _tuners[who] = Tuner(host, port, folder, mode, limits)
        return t


def history(folder: Path, last: int = 30) -> list[dict]:
    f = folder / "autoguide.jsonl"
    try:
        lines = f.read_text(encoding="utf-8").splitlines()[-last:]
    except OSError:
        return []
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out
