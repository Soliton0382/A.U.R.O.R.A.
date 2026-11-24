# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N152 phase 0 bench (sys/core/desk/bench): the guards and the oracles, without starting the bench.

The bench itself (virtual KWin, portals, AT-SPI) never starts in the suite: it runs by hand with run_phase0.py.
Every test here skips where the bench cannot exist (not Linux, no kwin_wayland: CI, the Mac and Windows ports)."""
import os
import shutil
import sys
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[1]
DESK = CORE / "desk"

linux_bench = pytest.mark.skipif(not sys.platform.startswith("linux") or not shutil.which("kwin_wayland"),
                                 reason="no virtual KWin here (CI, ports): the N152 bench cannot exist")


def _env(rt: Path, **over) -> dict:
    e = {"XDG_RUNTIME_DIR": str(rt), "DBUS_SESSION_BUS_ADDRESS": "unix:abstract=/tmp/dbus-bench",
         "WAYLAND_DISPLAY": "wayland-banco", "DBUS_SYSTEM_BUS_ADDRESS": f"unix:path={rt}/no-system-bus"}
    e.update(over)
    return {k: v for k, v in e.items() if v is not None}


@linux_bench
def test_guard_refuses_the_real_session(tmp_path):
    from desk.bench import guard
    rt = tmp_path / "rt"
    rt.mkdir(mode=0o700)
    guard.check_env(_env(rt))                                         # the bench's own: accepted
    real = f"/run/user/{os.getuid()}"
    bad = [
        {"XDG_RUNTIME_DIR": real},
        {"DBUS_SESSION_BUS_ADDRESS": f"unix:path={real}/bus"},
        {"WAYLAND_DISPLAY": "wayland-0"},
        {"WAYLAND_DISPLAY": f"{real}/wayland-0"},
        {"DISPLAY": ":0"},
        {"DBUS_SYSTEM_BUS_ADDRESS": "unix:path=/run/dbus/system_bus_socket"},
        {"DBUS_SYSTEM_BUS_ADDRESS": None},
    ]
    for over in bad:
        env = _env(rt, **over)
        if over.get("XDG_RUNTIME_DIR") == real:
            env["DBUS_SYSTEM_BUS_ADDRESS"] = f"unix:path={real}/no-system-bus"
        with pytest.raises(guard.BenchRefused):
            guard.check_env(env)


@linux_bench
def test_guard_wants_a_private_runtime_dir(tmp_path):
    from desk.bench import guard
    rt = tmp_path / "rt"
    rt.mkdir(mode=0o755)
    os.chmod(rt, 0o755)
    with pytest.raises(guard.BenchRefused):
        guard.check_env(_env(rt))


def test_nothing_imports_the_bench():
    """The bench (and its consent clickers) is never imported by aurora-desk's code nor by Aurora (§13.1).
    One exception, by design (bozza 7 §1, «Prova sul banco»): the app may START desk/bench/lib_run.py as a process
    of its own, which re-executes inside the bench's dbus-run-session behind guard.check_env (never the real bus or
    display), so the bench's consent clicker can never see the owner's portal. Changed on 25 Nov and recorded in
    MEASUREMENTS M337: the launch is allowed, an import is not."""
    offenders = []
    for top in (CORE / "aurora", CORE / "script", DESK):
        for p in top.rglob("*.py"):
            if "bench" in p.relative_to(CORE).parts:
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            rel = str(p.relative_to(CORE))
            if "desk.bench" in text or "from desk import bench" in text or "consent.py" in text \
                    or "p4_measure" in text:
                offenders.append(rel)
            elif "desk/bench" in text:
                ok = rel == "desk/app/aurora_desk.py" and text.count("desk/bench") == 1 \
                    and 'CORE / "desk/bench/lib_run.py"' in text
                if not ok:
                    offenders.append(rel)
    assert offenders == []


def test_f1_pixel_oracle_sees_a_wrong_order():
    np = pytest.importorskip("numpy")
    pytest.importorskip("gi")                                          # f1 imports the KWin script runner (Gio)
    from desk.bench import f1
    W, H = 40, 30
    frame = np.zeros((H, W, 4), dtype=np.uint8)
    frame[5:20, 5:25, :3] = (255, 0, 0)                               # bottom window
    frame[10:25, 15:35, :3] = (0, 0, 255)                             # top window, overlapping
    ours = [{"caption": "a", "frame": [5, 5, 20, 15]}, {"caption": "b", "frame": [15, 10, 20, 15]}]
    colour = {"a": (255, 0, 0), "b": (0, 0, 255)}
    assert f1.compare_frame(frame.tobytes(), W, H, ours, colour)["bad_pixels"] == 0
    assert f1.compare_frame(frame.tobytes(), W, H, list(reversed(ours)), colour)["bad_pixels"] > 0
