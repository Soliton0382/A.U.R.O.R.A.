# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N.I.N.A.'s pointing read back (the inventory script 5): the first attempt of each centering is the mount's error, a
recenter after a flip gives cone + non-orthogonality, two flips apart in declination give each. Invented log lines in
N.I.N.A.'s own format."""
import math

from aurora import ast_inventory, ast_pointing as P


def hms(deg):
    h = deg / 15
    a, b = int(h), int((h - int(h)) * 60)
    return f"{a:02d}:{b:02d}:{round((h - a - b / 60) * 3600):02d}"


def dms(deg):
    s = "-" if deg < 0 else ""
    deg = abs(deg)
    a, b = int(deg), int((deg - int(deg)) * 60)
    return f"{s}{a:02d}° {b:02d}' {round((deg - a - b / 60) * 3600):02d}\""


def c(ra, dec):
    return f"RA: {hms(ra)}; Dec: {dms(dec)}; Epoch: JNOW"


def centering(at, scope, aim, solved):
    return (f"{at}.1234|INFO|CenteringSolver.cs|Center|99|Centering Solver - Scope Position: {c(*scope)}; Offset: "
            f"RA: 00:00:00; Dec: 00° 00' 00\"; Distance: 00° 00' 00\"; Bearing: 00° 00' 00\"; Centering Coordinates: "
            f"{c(*aim)}; Solved: {c(*solved)}; Separation RA: 00:00:01; Dec: 00° 00' 10\"; Distance: 00° 00' 12\"; "
            f"Bearing: 00° 00' 00\"; Threshold: 1")


def flip(at):
    return f"{at}.0001|INFO|MeridianFlipTrigger.cs|Execute|80|Meridian Flip - Starting meridian flip"


def night(cone_arcmin, np_arcmin, decs):
    lines, t = [], 20
    for dec in decs:
        aim = (90.0, dec)
        lines.append(centering(f"2026-01-10T{t:02d}:00:00", (90.1, dec + 0.05), aim, aim))   # off by 6′·cos δ, 3′
        lines.append(centering(f"2026-01-10T{t:02d}:00:30", aim, aim, aim))                   # the second attempt
        lines.append(flip(f"2026-01-10T{t:02d}:40:00"))
        jump = 2 * (cone_arcmin + np_arcmin * math.sin(math.radians(dec))) / 60               # degrees of RA·cos δ
        lines.append(centering(f"2026-01-10T{t:02d}:42:00", (90 + jump / math.cos(math.radians(dec)), dec), aim, aim))
        t += 1
    return lines


def test_the_first_attempt_is_the_error_the_next_ones_follow_the_sync():
    p = P.parse(night(2.0, 0.0, [20.0]))
    first = p["centerings"][0]
    assert first["attempts"] == 2 and abs(first["ra_arcmin"] - 6 * math.cos(math.radians(20))) < 0.3
    assert abs(first["dec_arcmin"] - 3.0) < 0.05 and len(p["centerings"]) == 2 and not p["flips_guessed"]


def test_a_flip_gives_cone_and_non_orthogonality_at_its_declination():
    j = P.flip_jumps(P.parse(night(2.0, 1.0, [30.0])))
    assert len(j) == 1 and abs(j[0]["c_np_arcmin"] - 2.5) < 0.15 and j[0]["dec"] == 30.0
    assert P.square(j) is None                                  # one declination: the sum only


def test_two_flips_apart_in_declination_tell_cone_from_non_orthogonality():
    sq = P.square(P.flip_jumps(P.parse(night(3.0, 2.0, [0.0, 60.0]))))
    assert abs(sq["cone_arcmin"] - 3.0) < 0.2 and abs(sq["np_arcmin"] - 2.0) < 0.3


def test_without_a_flip_line_a_recenter_of_the_same_object_is_taken_and_said():
    lines = [x for x in night(2.0, 0.0, [10.0]) if "Meridian" not in x]
    p = P.parse(lines)
    assert p["flips_guessed"] and len(P.flip_jumps(p)) == 1 and "dedotto" in P.text(p)


def test_the_inventory_carries_the_section_and_other_lines_are_left_out():
    text = ("# astro inventory 2026-01-11 10:00 (script 5)\n== N.I.N.A. pointing (the last logs: plate solving)\n"
            "-- log: 20260110.log\n  " + "\n  ".join(night(1.0, 0.0, [15.0]))
            + "\n  2026-01-10T23:00:00.1|INFO|X.cs|Y|1|Platesolve successful: Coordinates: RA: 01:00:00\n")
    p = ast_inventory.parse(text)
    assert p["script"] == 5 and len(p["pointing"]["centerings"]) == 2
    assert "2 centrature" in P.text(p["pointing"]) and P.text({"centerings": [], "flips": []}).startswith("Nessuna")
