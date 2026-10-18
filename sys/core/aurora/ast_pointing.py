# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔭 Where the mount thought it pointed and where it did (owner, 19 Oct: «teniamo aurora in monitoraggio per capire dove
potrebbe stare il problema… l'ortogonalità della montatura»; «estendi lo script per il log di nina»). Read only: the lines
the inventory script (version 5) copies from N.I.N.A.'s last logs — its centering solver's «Scope Position … Solved …»,
one per attempt, and the meridian flips.

The first attempt of each centering is the mount's pointing error there (scope − solved: RA·cos δ and Dec, arcminutes);
the next attempts only follow the sync. The meridian flip is the measure of a mount's squareness: N.I.N.A. recenters
the same object right after it (Recenter), and the error the mount then shows on the other side of the pier, against the
one it was synced to, is 2·(C + NP·sin δ) in RA·cos δ — C the cone (tube not square to the Dec axis), NP the Dec axis not
square to the RA axis. One flip gives the sum at its declination; two flips at declinations apart give C and NP. The
polar error, the same on both sides, does not jump at a flip. N.I.N.A. writes RA to the second of time and Dec to the
arcsecond: enough for arcminutes. The sign of C and NP depends on the side the driver calls East: only sizes are said."""
from __future__ import annotations

import math
import re
from datetime import datetime

COORD = r"RA: (-?\d+):(\d+):(\d+); Dec: (-?)(\d+)° (\d+)' (\d+)\""
LINE = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)[.\d]*\|(\w+)\|[^|]*\|[^|]*\|\d*\|(.*)$")
CENTER = re.compile(r"Scope Position: " + COORD + r".*?Centering Coordinates: " + COORD + r".*?Solved: " + COORD)
SAME_TARGET_ARCMIN = 30.0         # two centerings this close in what they aimed at are on the same object
GAP_S = 180                       # attempts of one centering follow each other within this


def _coord(g: tuple) -> tuple[float, float]:
    h, m, s, sign, d, dm, ds = g
    ra = (abs(int(h)) + int(m) / 60 + int(s) / 3600) * 15
    dec = int(d) + int(dm) / 60 + int(ds) / 3600
    return ra, -dec if sign == "-" else dec


def _arcmin(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    """a − b as (RA·cos δ, Dec) in arcminutes."""
    dra = ((a[0] - b[0] + 180) % 360) - 180
    return dra * math.cos(math.radians(b[1])) * 60, (a[1] - b[1]) * 60


def parse(lines: list[str]) -> dict:
    """The section's lines → {"centerings": [first attempts], "flips": [times]}."""
    attempts, flips = [], []
    for raw in lines:
        m = LINE.match(raw.strip())
        if not m:
            continue
        at = datetime.fromisoformat(m.group(1))
        msg = m.group(3)
        if c := CENTER.search(msg):
            g = c.groups()
            attempts.append({"at": at, "scope": _coord(g[0:7]), "aim": _coord(g[7:14]), "solved": _coord(g[14:21])})
        elif re.search(r"(?i)meridian ?flip", msg) and re.search(r"(?i)start|begin|perform|initiat", msg):
            flips.append(at)
    out, last = [], None
    for a in attempts:
        fresh = (last is None or (a["at"] - last["at"]).total_seconds() > GAP_S
                 or max(map(abs, _arcmin(a["aim"], last["aim"]))) > 1.0)
        if fresh:
            ra, dec = _arcmin(a["scope"], a["solved"])
            out.append({"at": a["at"].isoformat(), "aim": a["aim"], "ra_arcmin": round(ra, 2), "dec_arcmin": round(dec, 2),
                        "arcmin": round(math.hypot(ra, dec), 2), "attempts": 1})
        else:
            out[-1]["attempts"] += 1
        last = a
    guessed = False
    if not flips:                                     # no flip line: a later centering of the same object is its recenter
        guessed = True
        flips = [b["at"] for a, b in zip(out, out[1:]) if max(map(abs, _arcmin(b["aim"], a["aim"]))) <= SAME_TARGET_ARCMIN]
        flips = [datetime.fromisoformat(f) for f in flips]
    return {"centerings": out, "flips": [f.isoformat() for f in flips], "flips_guessed": guessed}


def flip_jumps(p: dict) -> list[dict]:
    """Each flip with a centering of the same object before and after it: the jump, and C + NP·sin δ (its half)."""
    out, cs = [], p["centerings"]
    for f in p["flips"]:
        before = [c for c in cs if c["at"] < f]
        after = [c for c in cs if c["at"] >= f]
        if not before or not after:
            continue
        b, a = before[-1], after[0]
        if max(map(abs, _arcmin(a["aim"], b["aim"]))) > SAME_TARGET_ARCMIN:
            continue
        out.append({"at": f, "dec": round(a["aim"][1], 1), "jump_arcmin": round(a["ra_arcmin"], 2),
                    "c_np_arcmin": round(abs(a["ra_arcmin"]) / 2, 2), "dec_jump_arcmin": round(a["dec_arcmin"], 2)})
    return out


def square(jumps: list[dict]) -> dict | None:
    """C and NP from flips at declinations at least 20° apart (least squares on C + NP·sin δ = jump/2), or None."""
    if len(jumps) < 2 or max(j["dec"] for j in jumps) - min(j["dec"] for j in jumps) < 20:
        return None
    s = [math.sin(math.radians(j["dec"])) for j in jumps]
    y = [j["jump_arcmin"] / 2 for j in jumps]
    n, ss, sy, s1, y1 = len(s), sum(v * v for v in s), sum(a * b for a, b in zip(s, y)), sum(s), sum(y)
    det = n * ss - s1 * s1
    if abs(det) < 1e-9:
        return None
    np_ = (n * sy - s1 * y1) / det
    c = (y1 - np_ * s1) / n
    return {"cone_arcmin": round(abs(c), 2), "np_arcmin": round(abs(np_), 2), "flips": n}


def text(p: dict) -> str:
    cs = p["centerings"]
    if not cs:
        return ("Nessuna centratura nei log di N.I.N.A. dell'inventario: serve lo script 5 eseguito dopo una notte con "
                "Center o Slew and center.")
    errs = sorted(c["arcmin"] for c in cs)
    lines = [f"{len(cs)} centrature: errore di puntamento al primo tentativo mediana {errs[len(errs) // 2]:.1f}′, "
             f"massimo {errs[-1]:.1f}′ (dopo un sync è la differenza tra due punti del cielo: modello della montatura e "
             "flessioni, non l'allineamento polare da solo)."]
    jumps = flip_jumps(p)
    for j in jumps:
        lines.append(f"Flip{' (dedotto dal ricentraggio)' if p.get('flips_guessed') else ''} del {j['at'][:10]} a Dec {j['dec']:+.0f}°: salto di {abs(j['jump_arcmin']):.1f}′ in RA → "
                     f"cono + non ortogonalità ≈ {j['c_np_arcmin']:.1f}′ a quella declinazione.")
    sq = square(jumps)
    if sq:
        lines.append(f"Da {sq['flips']} flip: cono ≈ {sq['cone_arcmin']:.1f}′, assi non ortogonali ≈ {sq['np_arcmin']:.1f}′.")
    elif not jumps:
        lines.append("Nessun flip con il ricentraggio dello stesso oggetto: il cono e l'ortogonalità si misurano lì.")
    else:
        lines.append("Per separare cono e ortogonalità serve un altro flip a una declinazione lontana almeno 20°.")
    return "\n".join(lines)
