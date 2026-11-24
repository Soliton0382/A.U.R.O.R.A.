# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N152 version 1: the personal library and the accessibility switch (design bozza 7 §2, bozza 8 §2, §4).

- personal library: ~/.local/state/aurora-desk/library/ (0700), drafts in bozze/<os>/<program>/<name>.json (0600),
  examples kept apart in <name>.esempi.json (0600), only the ones the owner keeps; never under usr/, never backed up;
- the accessibility switch persists in dconf (M334 P1): before turning it on, the value before and the value written
  are saved in a11y.json; it is put back only if it still holds the value written (the owner may have changed it);
- the app's runtime folder: $XDG_RUNTIME_DIR/aurora-desk (0700): lock, stop files."""
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path

STATE = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "aurora-desk"
LIBRARY = STATE / "library"
DRAFTS = LIBRARY / "bozze"
BENCH = STATE / "bench"
A11Y = STATE / "a11y.json"
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,59}$")


def private_dir(p: Path) -> Path:
    """Create p (0700) or check it: ours, 0700, not a link."""
    p.mkdir(parents=True, exist_ok=True, mode=0o700)
    st = os.lstat(p)
    if os.path.islink(p) or st.st_uid != os.getuid():
        raise PermissionError(f"{p}: not ours or a link")
    if st.st_mode & 0o077:
        os.chmod(p, 0o700)
    return p


def runtime_dir() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR")
    if not base:
        raise RuntimeError("no XDG_RUNTIME_DIR")
    return private_dir(Path(base) / "aurora-desk")


def single_instance():
    """A lock in the runtime folder: one aurora-desk at a time. Returns the open file (keep it) or None."""
    f = open(runtime_dir() / "lock", "a")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


def write_private(path: Path, data: str) -> None:
    """Write a 0600 file without following a link; replace atomically."""
    private_dir(path.parent)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(data)
    os.replace(tmp, path)


# --- the accessibility switch -------------------------------------------------------------------------------------

def _bus():
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio
    return Gio.bus_get_sync(Gio.BusType.SESSION, None)


def a11y_enabled() -> bool:
    from gi.repository import Gio, GLib
    r = _bus().call_sync("org.a11y.Bus", "/org/a11y/bus", "org.freedesktop.DBus.Properties", "Get",
                         GLib.Variant("(ss)", ("org.a11y.Status", "IsEnabled")), None, Gio.DBusCallFlags.NONE,
                         3000, None)
    return bool(r.unpack()[0])


def _set_a11y(on: bool) -> None:
    from gi.repository import Gio, GLib
    _bus().call_sync("org.a11y.Bus", "/org/a11y/bus", "org.freedesktop.DBus.Properties", "Set",
                     GLib.Variant("(ssv)", ("org.a11y.Status", "IsEnabled", GLib.Variant("b", on))), None,
                     Gio.DBusCallFlags.NONE, 3000, None)


def a11y_on() -> dict:
    """Turn accessibility on for a demonstration, remembering the value before."""
    before = a11y_enabled()
    rec = {"before": before, "wrote": True}
    if not A11Y.exists():                               # an older record wins: it holds the owner's real «before»
        write_private(A11Y, json.dumps(rec))
    if not before:
        _set_a11y(True)
    return rec


def a11y_restore() -> str:
    """Put the switch back: only if it still holds what aurora-desk wrote. Returns what was done."""
    if not A11Y.exists():
        return "nothing recorded"
    rec = json.loads(A11Y.read_text())
    now = a11y_enabled()
    if now != rec.get("wrote"):
        A11Y.unlink()
        return "changed by someone else meanwhile: left as it is"
    if rec.get("before") != now:
        _set_a11y(bool(rec.get("before")))
    A11Y.unlink()
    return f"back to {rec.get('before')}"


# --- the personal library -----------------------------------------------------------------------------------------

def draft_path(os_: str, program: str, name: str) -> Path:
    if not NAME.match(name) or not NAME.match(program):
        raise ValueError("a name: lowercase letters, digits and «-», up to 60")
    return DRAFTS / os_ / program / f"{name}.json"


def save_draft(proc: dict, os_: str, program: str, name: str, examples_kept: dict) -> dict:
    """Validate as a personal procedure and save; returns {"path", "sha256", "errors"}."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from desk import library_check
    path = draft_path(os_, program, name)
    proc = dict(proc, id=f"per:{os_}/{program}/{name}")
    raw = json.dumps(proc, ensure_ascii=False, indent=1)
    probe = BENCH / "check" / os_ / program / f"{name}.json"   # checked in place before saving
    write_private(probe, raw)
    errs = library_check.check(probe, BENCH / "check", ns="per")
    probe.unlink()
    if errs:
        return {"path": None, "sha256": None, "errors": errs}
    write_private(path, raw)
    if examples_kept:
        write_private(path.with_name(f"{name}.esempi.json"), json.dumps(examples_kept, ensure_ascii=False))
    return {"path": str(path), "sha256": hashlib.sha256(raw.encode()).hexdigest(), "errors": []}


def list_drafts() -> list:
    out = []
    if DRAFTS.exists():
        for f in sorted(DRAFTS.rglob("*.json")):
            if f.name.endswith(".esempi.json"):
                continue
            out.append(f)
    return out
