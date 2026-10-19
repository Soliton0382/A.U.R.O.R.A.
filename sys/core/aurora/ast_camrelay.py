# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📡 A camera of the telescope's PC relayed through Aurora (owner, 19 Oct: «creare una sorta di server da installare nel
mini PC in modo che invii in streaming quello che vede la camera che si sceglie»). The PC sends, Aurora never calls it:
no port opened on the PC. Its script (astro_camera.ps1) tells Aurora the cameras it sees, asks which one is wanted, and
sends that one with ffmpeg as JPEG frames in one long POST (mpjpeg: «--ffmpeg», a Content-length, the JPEG). Aurora
keeps the last frame and hands it to the person's pages (the live collimation), as a picture or a stream.

The PC holds a camera key, not a person's login: made by the person in their page, kept here only as its hash, it may
only send frames and read which camera is wanted — never read anything of Aurora. One key a person; a new one replaces
the old. Frames live in memory only, never written."""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
import time
from pathlib import Path

MAX_FRAME = 8 * 1024 * 1024          # a JPEG bigger than this is not a camera's frame
STALE_S = 10.0                       # no frame for this long: the camera is not live
# what the page may ask of the PC's camera (OpenCV's properties, as the collimator's own program sets them): numbers
# within these bounds, the camera saying back what it took; the resolution and the stream's size and pace
CONTROLS = ("brightness", "contrast", "saturation", "sharpness", "gamma", "gain", "exposure", "focus", "zoom")
SWITCHES = ("auto_exposure", "autofocus")
SIZES = ((1280, 720), (1920, 1080), (2592, 1944), (3840, 2160))
HEAD = re.compile(rb"--[^\r\n]*\r\n(?:[^\r\n]+\r\n)*?Content-length: *(\d+)\r\n(?:[^\r\n]+\r\n)*\r\n", re.I)


class Frames:
    """mpjpeg bytes in, whole JPEG frames out; a part too big or a stream out of step said by an error."""

    def __init__(self):
        self.buf = b""

    def feed(self, data: bytes) -> list[bytes]:
        self.buf += data
        out = []
        while True:
            m = HEAD.search(self.buf)
            if not m:
                if len(self.buf) > MAX_FRAME:
                    raise ValueError("not an mpjpeg stream")
                return out
            n = int(m.group(1))
            if n > MAX_FRAME:
                raise ValueError("a frame too big")
            end = m.end() + n
            if len(self.buf) < end:
                return out
            frame = self.buf[m.end():end]
            self.buf = self.buf[end:]
            if frame[:2] == b"\xff\xd8":
                out.append(frame)


class Relay:
    """The keys (by hash, with their person) in the status folder; cameras, choice and last frame in memory."""

    def __init__(self, status_dir: Path):
        self.file = Path(status_dir) / "camera_keys.json"
        self.lock = threading.Lock()
        self.state: dict[str, dict] = {}

    def _keys(self) -> dict:
        try:
            d = json.loads(self.file.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _hash(key: str) -> str:
        return hashlib.sha256(key.encode()).hexdigest()

    def new_key(self, user: str) -> str:
        """A new key for the person, the old one forgotten; given once."""
        key = "aurcam_" + secrets.token_urlsafe(24)
        keys = {h: v for h, v in self._keys().items() if v.get("user") != user}
        keys[self._hash(key)] = {"user": user, "made": round(time.time())}
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self.file.write_text(json.dumps(keys), encoding="utf-8")
        return key

    def who(self, key: str) -> str | None:
        if not key or not key.startswith("aurcam_"):
            return None
        v = self._keys().get(self._hash(key))
        return v.get("user") if v else None

    def has_key(self, user: str) -> bool:
        return any(v.get("user") == user for v in self._keys().values())

    def _s(self, user: str) -> dict:
        return self.state.setdefault(user, {"devices": [], "wanted": "", "seen": 0.0, "frame": None, "at": 0.0, "n": 0,
                                            "rate": 0.0, "settings": {}, "version": 0, "camera": {}})

    def settings(self, user: str, change: dict) -> dict:
        """The page's asks for the camera, checked and merged; each change a new version the PC applies once."""
        out = {}
        for k, v in (change or {}).items():
            if k in CONTROLS:
                if v is None:
                    out[k] = None                      # back to the camera's own
                    continue
                v = float(v)
                if not -100000 <= v <= 100000:
                    raise ValueError(f"{k}: out of range")
                out[k] = v
            elif k in SWITCHES:
                out[k] = bool(v)
            elif k == "size":
                if list(v) not in [list(x) for x in SIZES]:
                    raise ValueError("size: one of " + ", ".join(f"{w}x{h}" for w, h in SIZES))
                out[k] = [int(v[0]), int(v[1])]
            elif k == "fps":
                out[k] = max(1, min(30, int(v)))
            elif k == "send_width":
                out[k] = 0 if int(v) <= 0 else max(320, min(4096, int(v)))
            elif k == "quality":
                out[k] = max(40, min(95, int(v)))
            elif k == "dialog":
                out[k] = True                          # the camera's own window, once, on the PC's screen (a counter)
            else:
                raise ValueError(f"unknown setting: {k}")
        with self.lock:
            st = self._s(user)
            if out.pop("dialog", None):
                st["dialog"] = st.get("dialog", 0) + 1
            st["settings"].update(out)
            st["settings"] = {k: v for k, v in st["settings"].items() if v is not None}
            st["version"] += 1
            return {"settings": dict(st["settings"]), "version": st["version"]}

    def pc(self, user: str, names: list, camera: dict | None) -> dict:
        """The PC's cameras and its camera's state told; the camera wanted and the settings answered."""
        with self.lock:
            s = self._s(user)
            s["devices"] = [str(x)[:120] for x in names][:20]
            s["seen"] = time.time()
            if isinstance(camera, dict):
                s["camera"] = {k: camera[k] for k in ("values", "size", "agent", "error") if k in camera}
            return {"wanted": s["wanted"], "settings": s["settings"], "version": s["version"], "dialog": s.get("dialog", 0)}

    def want(self, user: str, name: str) -> None:
        with self.lock:
            s = self._s(user)
            s["wanted"] = str(name)[:120]
            if not name:
                s["frame"] = None

    def wanted(self, user: str) -> str:
        with self.lock:
            s = self._s(user)
            s["seen"] = time.time()
            return s["wanted"]

    def put(self, user: str, frame: bytes) -> None:
        with self.lock:
            s = self._s(user)
            now = time.time()
            if s["at"]:
                s["rate"] = 0.8 * s["rate"] + 0.2 / max(1e-3, now - s["at"])
            s.update(frame=frame, at=now, n=s["n"] + 1, seen=now)

    def last(self, user: str) -> tuple[bytes | None, float]:
        with self.lock:
            s = self._s(user)
            fresh = s["frame"] is not None and time.time() - s["at"] < STALE_S
            return (s["frame"] if fresh else None), s["at"]

    def number(self, user: str) -> int:
        """How many frames came: a stream sends the last one when this grows."""
        with self.lock:
            return self._s(user)["n"]

    def status(self, user: str) -> dict:
        with self.lock:
            s = self._s(user)
            now = time.time()
            return {"devices": s["devices"], "wanted": s["wanted"], "pc_seen_s": round(now - s["seen"], 1) if s["seen"] else None,
                    "live": s["frame"] is not None and now - s["at"] < STALE_S, "fps": round(s["rate"], 1),
                    "key": self.has_key(user), "camera": s["camera"], "settings": s["settings"],
                    "controls": list(CONTROLS), "switches": list(SWITCHES), "sizes": [list(x) for x in SIZES]}
