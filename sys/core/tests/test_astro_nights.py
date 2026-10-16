# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔭 The nights already guided (ROADMAP N28): a PHD2 guide log, invented here, read back — the RMS over the frames that
count, the mount that stops at the meridian before N.I.N.A.'s flip, the Guiding Assistant's advice against the settings
in use, and nothing that gives the site back (altitude and azimuth dropped)."""
import json
import math

from aurora import ast_guidelog as G

COLS = ("Frame,Time,mount,dx,dy,RARawDistance,DECRawDistance,RAGuideDistance,DECGuideDistance,RADuration,RADirection,"
        "DECDuration,DECDirection,XStep,YStep,StarMass,SNR,ErrorCode")


def head(start: str, ha: float, pier: str, backlash: str = "disabled") -> list[str]:
    return [f"Guiding Begins at {start}", "Equipment Profile = Test guide scope",
            "Pixel scale = 2.00 arc-sec/px, Binning = 1, Focal length = 400 mm", "Exposure = 1000 ms",
            "Mount = TestMount (ASCOM), connected, guiding enabled", "X guide algorithm = Hysteresis, Control gain = 0.700",
            "Minimum move = 0.150", "Y guide algorithm = Resist Switch, Minimum move = 0.150 Aggression = 100% FastSwitch = enabled",
            f"Backlash comp = {backlash}, pulse = 120 ms", "Max RA duration = 500, Max DEC duration = 500, DEC guide mode = Auto",
            f"RA = 5.50 hr, Dec = 22.0 deg, Hour angle = {ha:.2f} hr, Pier side = {pier}, Rotator pos = N/A, Alt = 61.3 deg, Az = 171.7 deg",
            COLS]


def row(i: int, t: float, ra: float, dec: float, ra_ms: int = 50, err: int = 0, kind: str = "Mount") -> str:
    if kind == "DROP":
        return f'{i},{t:.3f},"DROP",,,,,,,,,,,,,0,0.00,2,"Star lost - low SNR"'
    return f'{i},{t:.3f},"Mount",0,0,{ra:.3f},{dec:.3f},0,0,{ra_ms},W,0,,,,500,30.00,{err}'


def log() -> str:
    lines = ["PHD2 version 2.6.14 [Windows], Log version 2.5. Log enabled at 2026-01-10 19:00:00",
             "INFO: GA Result - PA Error= 7.0 arc-min", "INFO: GA Result - Backlash= 200  +/-  50 ms (2.0  +/-  0.5 arc-sec)",
             "INFO: GA Result - Recommendation: Try starting with a Dec backlash compensation of 200 ms",
             "INFO: GA Result - Recommendation: Try setting Dec min-move to 0.25",
             "West calibration complete. Angle = 10.0 deg, Rate = 3.000 px/sec, Parity = Even", ""]
    # a quiet session of 40 frames: ±0.5 px RA, ±0.25 px DEC (×2″/px → RMS 1.0″ and 0.5″), a settling stretch and a
    # lost star that do not count
    lines += head("2026-01-10 19:10:00", -2.0, "West")
    for i in range(40):
        if i == 10:
            lines += ["INFO: SETTLING STATE CHANGE, Settling started", row(100, 9.5, 9.0, 9.0), "INFO: SETTLING STATE CHANGE, Settling complete"]
        if i == 20:
            lines.append(row(200, 19.5, 0, 0, kind="DROP"))
        lines.append(row(i, float(i), 0.5 if i % 2 else -0.5, 0.25 if i % 2 else -0.25))
    lines += ["Guiding Ends at 2026-01-10 19:10:40", ""]
    # a session that starts an hour before the meridian and, 59.8 min later, runs away in RA at the 500 ms limit
    lines += head("2026-01-10 20:00:00", -1.0, "West")
    for i in range(60):
        lines.append(row(i, i * 60.0, 0.1, -0.1))
    for k in range(8):
        lines.append(row(60 + k, 3590.0 + k, 4.0 + 5 * k, 0.0, ra_ms=500))
    lines += ["Guiding Ends at 2026-01-10 21:00:00", ""]
    return "\n".join(lines)


def test_rms_counts_only_the_frames_that_count():
    d = G.parse(log())
    s = d["sessions"][0]
    assert d["version"] == "2.6.14 [Windows]" and d["night"] == "2026-01-10"
    assert s["frames"] == 41 and s["counted"] == 40 and s["lost"] == 1              # the settling frame and the DROP out
    assert s["rms"]["ra"] == 1.0 and s["rms"]["dec"] == 0.5 and s["rms"]["total"] == round(math.hypot(1, .5), 2)
    assert s["settings"]["scale"] == 2.0 and s["settings"]["max_ra_ms"] == 500 and s["settings"]["backlash_on"] is False
    assert d["calibrations"] == [{"axis": "RA", "angle": 10.0, "rate": 3.0}]


def test_the_mount_that_stops_before_the_flip_is_said():
    d = G.parse(log())
    w = d["sessions"][1]["runaways"]
    assert len(w) == 1 and w[0]["axis"] == "ra" and w[0]["frames"] == 8 and w[0]["at"] == "20:59"
    assert w[0]["rate"] == 10.0                                                          # 5 px/s × 2″/px
    assert w[0]["meridian_min"] == 0                                                     # -1 h + 59.8 min sidereal
    assert d["sessions"][1]["rms"]["ra"] == 0.0                                          # the runaway is not the RMS
    f = G.findings(d, imaging_scale=1.5, flip={"MinutesAfterMeridian": "2", "MaxMinutesAfterMeridian": "5"})
    codes = {x["code"]: x for x in f}
    assert codes["runaway_meridian"]["flip_after"] == 2.0 and codes["runaway_meridian"]["level"] == "high"
    assert codes["polar"]["arcmin"] == 7.0 and codes["backlash_off"]["ms"] == 200
    assert codes["min_move"]["axis"] == "DEC" and codes["min_move"]["advised"] == 0.25
    assert "star_lost" not in codes                                                       # 1 in 41 is not a problem


def test_nothing_of_the_site_is_kept():
    d = G.parse(log())
    text = json.dumps(d)
    assert "61.3" not in text and "171.7" not in text and "Alt" not in text              # altitude and azimuth dropped
    assert d["sessions"][0]["settings"]["ha_h"] == -2.0                                   # the hour angle, rounded


def test_the_folder_gives_the_guide_logs_only(tmp_path):
    (tmp_path / "PHD2_GuideLog_2026-01-10_190000.txt").write_text(log(), encoding="utf-8")
    (tmp_path / "PHD2_DebugLog_2026-01-10_190000.txt").write_text("PHD2 version 2.6.14 debug", encoding="utf-8")
    (tmp_path / "astro_inventory.txt").write_text("# astro inventory\n", encoding="utf-8")
    (tmp_path / "empty_GuideLog.txt").write_text("PHD2 version 2.6.14 [Windows], Log version 2.5. Log enabled at 2026-01-11 19:00:00\n",
                                                 encoding="utf-8")
    got = G.nights(tmp_path, 1.5)
    assert [n["file"] for n in got] == ["PHD2_GuideLog_2026-01-10_190000.txt"]            # no debug log, no empty night
    assert got[0]["advice_from"] == "2026-01-10" and got[0]["findings"]


def jumpy(kind: str) -> str:
    """A quiet session of 1200 frames at 1 s with, at frame 600, a jump of 3 px in DEC that stays («gremlin») or a
    single frame off and back («glitch»); and RA twice DEC's scatter all along (elongated stars)."""
    lines = ["PHD2 version 2.6.14 [Windows], Log version 2.5. Log enabled at 2026-01-12 19:00:00"]
    lines += head("2026-01-12 20:00:00", -3.0, "West")
    for i in range(1200):
        ra = 0.4 if i % 2 else -0.4
        dec = 0.2 if i % 2 else -0.2
        if kind == "gremlin" and 600 <= i < 610:
            dec += 3.0
        if kind == "glitch" and i == 600:
            dec += 3.0
        lines.append(row(i, float(i), ra, dec))
    lines += ["Guiding Ends at 2026-01-12 20:20:00"]
    return "\n".join(lines)


def test_a_jump_that_stays_is_a_gremlin_one_frame_is_not():
    g = G.parse(jumpy("gremlin"))["sessions"][0]
    assert g["gremlins"]["n"] == 1 and g["gremlins"]["at"] == ["20:10"]
    assert G.parse(jumpy("glitch"))["sessions"][0]["gremlins"]["n"] == 0
    codes = {f["code"]: f for f in G.findings(G.parse(jumpy("none")))}
    assert codes["elongated"]["axis"] == "RA"                                             # 0.8″ against 0.4″: twice
