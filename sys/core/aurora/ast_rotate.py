# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔭 The camera turned by hand to the framing's angle, without a rotator (owner, 19 Oct: «il mosaico non lo posso più
fare a meno che Aurora non mi aiuta a girare la camera… perfettamente allineata con la rotazione di n.i.n.a»).

One step: a frame taken and plate solved by N.I.N.A. itself (Advanced API: camera/capture with solve — the person's
own solver and its plate-solving exposure; nothing else is moved), its position angle against the one wanted (given,
or N.I.N.A.'s framing assistant's), and what to do: «gira di 2,4° in senso orario guardando la camera da dietro».
A rectangle at θ and θ + 180° frames the same (N.I.N.A. holds them equal), so the turn is never more than 90°.
Which way of turning raises the angle depends on the optics (a mirror more or less), not on the night: the first time
it is not known, the person is told one way, and the next solve learns it (astro_setup.json "rotation"); a mirrored
solve («Flipped») is kept apart. Done within TOL_DEG: a mosaic's panels then meet within a few arcseconds."""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from .sys_lang import say as _t   # each sentence in the reader's language (C526)

PORT = 1888
TOL_DEG = 0.3
LEARN_S = 1800          # a turn told and measured within this is the same turn
MIN_SEEN = 0.2          # a change smaller than this taught nothing (the solve's own noise)


def wrap90(d: float) -> float:
    """An angle difference on a rectangle: in [-90, 90)."""
    return (float(d) + 90.0) % 180.0 - 90.0


def capture(host: str, port: int = PORT, timeout: float = 180.0) -> dict:
    """N.I.N.A. takes and solves one frame: {"pa", "flipped", "ra_deg", "dec_deg", "scale"} or {"error"}."""
    q = urllib.parse.urlencode({"solve": "true", "waitForResult": "true", "omitImage": "true", "save": "false"})
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/v2/api/equipment/camera/capture?{q}",  # noqa: S310
                                    timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
    except (OSError, ValueError) as e:
        return {"error": _t(f"N.I.N.A. non risponde ({type(e).__name__}): è acceso, con l'Advanced API attiva?", f"N.I.N.A. does not answer ({type(e).__name__}): is it on, with the Advanced API enabled?")}
    if not d.get("Success", False):
        return {"error": str(d.get("Error") or d.get("Response") or _t("errore di N.I.N.A.", "an error of N.I.N.A."))[:200]}
    s = (d.get("Response") or {}).get("PlateSolveResult") or {}
    if not s.get("Success"):
        return {"error": _t("plate solving non riuscito: stelle a fuoco? posa di plate solving abbastanza lunga?", "plate solving failed: stars in focus? a plate-solving exposure long enough?")}
    c = s.get("Coordinates") or {}
    return {"pa": float(s["PositionAngle"]), "flipped": bool(s.get("Flipped")), "ra_deg": c.get("RADegrees"),
            "dec_deg": c.get("DECDegrees"), "scale": s.get("PixelScale")}


def framing_angle(host: str, port: int = PORT) -> float | None:
    """The rotation set in N.I.N.A.'s framing assistant (whole degrees), if it is open."""
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/v2/api/framing/info", timeout=5) as r:  # noqa: S310
            d = json.loads(r.read().decode("utf-8", "replace"))
        rect = ((d.get("Response") or {}).get("Rectangle") or {})
        v = rect.get("TotalRotation", rect.get("Rotation"))
        return float(v) if v is not None else None
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def step(solved: dict, want: float, state: dict, now: float | None = None) -> tuple[dict, dict]:
    """(what to say, the state to keep). state: {"cw_raises": {"n"|"f": bool}, "last": {pa, at, told, parity}}."""
    now = time.time() if now is None else now
    parity = "f" if solved["flipped"] else "n"
    learned = dict(state.get("cw_raises") or {})
    last = state.get("last") or {}
    out = {"pa": round(solved["pa"], 2), "want": round(float(want), 2)}
    if last.get("told") and last.get("parity") == parity and now - float(last.get("at", 0)) <= LEARN_S:
        seen = wrap90(solved["pa"] - float(last["pa"]))
        if abs(seen) >= MIN_SEEN:
            learned[parity] = (seen > 0) == (last["told"] == "cw")
            out["learned"] = _t(f"girando in senso {'orario' if last['told'] == 'cw' else 'antiorario'} l'angolo è "
                                f"{'salito' if seen > 0 else 'sceso'} di {abs(seen):.1f}°",
                                f"turning {'clockwise' if last['told'] == 'cw' else 'anticlockwise'} the angle went "
                                f"{'up' if seen > 0 else 'down'} by {abs(seen):.1f}°")
    d = wrap90(float(want) - solved["pa"])
    out["turn"] = round(d, 2)
    if abs(d) <= TOL_DEG:
        out.update(done=True, say=_t(f"✅ Allineata: {solved['pa']:.1f}° contro {float(want):.1f}° voluti "
                                  f"(scarto {d:+.2f}°, tolleranza ±{TOL_DEG}°). Stringi il Twist Lock senza ruotare.", f"✅ Aligned: {solved['pa']:.1f}° against the {float(want):.1f}° wanted "
                                  f"({d:+.2f}° off, tolerance ±{TOL_DEG}°). Tighten the Twist Lock without rotating."))
        return out, {"cw_raises": learned, "last": {}}
    if parity in learned:
        told = "cw" if (d > 0) == learned[parity] else "ccw"
        sure = True
    else:
        told, sure = "cw", False
    way = "orario" if told == "cw" else "antiorario"
    way_en = "clockwise" if told == "cw" else "anticlockwise"
    out.update(done=False, told=told, sure=sure,
               say=_t((f"Gira la camera di {abs(d):.1f}° in senso {way}, guardandola da dietro (dal lato del cavo)."
                       if sure else
                       f"Gira la camera di circa {abs(d):.1f}° in senso {way}, guardandola da dietro: è la prima volta, "
                       "il prossimo scatto mi dice se era il verso giusto e da lì in poi lo so.") + " Poi chiedimi di nuovo.",
                      (f"Turn the camera {abs(d):.1f}° {way_en}, looking at it from behind (the cable's side)."
                       if sure else
                       f"Turn the camera about {abs(d):.1f}° {way_en}, looking at it from behind: it is the first time, "
                       "the next shot tells me whether that was the right way and from then on I know.") + " Then ask me again."))
    return out, {"cw_raises": learned, "last": {"pa": solved["pa"], "at": now, "told": told, "parity": parity}}


def run(cfg, want: float | None = None) -> dict:
    """One step for the person whose configuration this is: solve, compare, say, remember."""
    from . import ast_advice, ast_inventory
    folder = ast_inventory.folder(cfg)
    host, _ = ast_advice.telescope_host(cfg)
    if not host:
        return {"error": _t("nessun indirizzo del PC del telescopio (AURORA_ASTRO_PC o l'inventario)", "no address of the telescope's PC (AURORA_ASTRO_PC or the inventory)")}
    if want is None:
        want = framing_angle(host)
        if want is None:
            return {"error": _t("dimmi l'angolo voluto (in gradi, come in N.I.N.A.) o apri l'assistente di inquadratura", "tell me the angle wanted (in degrees, as in N.I.N.A.) or open the framing assistant")}
    solved = capture(host)
    if "error" in solved:
        return solved
    out, state = step(solved, float(want), ast_advice.setup(folder).get("rotation") or {})
    ast_advice.save_part(folder, "rotation", state)
    return out
