# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔭 The words of a collimation read by ast_ocal: what each measure means and which screws to turn, in the reader's
language (C526). Moved here as it was from ast_ocal (which measures; this one only says): the three steps on a picture
(the secondary's tilt, its roundness and place, the primary) and the three on the live view (C365). Each line keeps its
code, so a page can tell them apart without reading the words."""
from __future__ import annotations

import math

from .ast_ocal import PLACE_TOL, ROUND_OK, SPOT_OK
from .sys_lang import say as _t


def _live(o: dict) -> list[dict]:
    """The three steps on the live view (C365), the centre spot hidden behind the secondary's reflection: 1) the
    primary's reflection centred in the drawtube (the secondary's tilt), 2) the secondary's border where the offset puts
    it, 3) the secondary's reflection — the dark disk the collimator sits in — on the focuser's axis (the primary)."""
    from .ast_stars import way
    sec, d, ref, sh, out = o["secondary"], o["drawtube"], o["reflection"], o["shadow"], []

    def step(code, n, what, p, screws):
        off = math.hypot(p["x"] - d["x"], p["y"] - d["y"]) / sec["r"]
        ok = off <= SPOT_OK
        to = way(round(math.degrees(math.atan2(p["y"] - d["y"], p["x"] - d["x"]))))
        out.append({"code": code, "ok": ok,
                    "text": _t(f"{n}) {what}: al centro del drawtube (scarto {off:.1%} del raggio del secondario)" if ok else
                            f"{n}) {what}: spostato verso {to} di {off:.1%} del raggio del secondario rispetto al centro "
                            f"del drawtube — {screws}", f"{n}) {what}: at the centre of the drawtube ({off:.1%} of the secondary's radius off)" if ok else
                            f"{n}) {what}: off towards {to} by {off:.1%} of the secondary's radius from the centre "
                            f"of the drawtube — {screws}")})
    step("secondary_tilt", 1, _t("inclinazione del secondario, il riflesso del primario", "the secondary's tilt, the primary's reflection"), ref, _t("le 3 viti del secondario", "the secondary's 3 screws"))
    e = o.get("expected")
    if e:
        top = max(abs(e["lo"]), abs(e["hi"])) + PLACE_TOL
        ok = e["across"] <= PLACE_TOL and e["along"] <= top
        out.append({"code": "secondary_place", "ok": ok,
                    "text": _t(f"2) posizione del secondario: il bordo è {e['along']:.1%} del suo raggio lungo il tubo (atteso "
                            f"fino a {top:.0%}) e {e['across']:.1%} di traverso"
                            + ("" if ok else " — " + ("di traverso: rotazione del secondario" if e["across"] > PLACE_TOL
                                                      else "lungo il tubo: vite centrale del secondario")), f"2) the secondary's place: the edge is {e['along']:.1%} of its radius along the tube (expected "
                            f"up to {top:.0%}) and {e['across']:.1%} across"
                            + ("" if ok else " — " + ("across: the secondary's rotation" if e["across"] > PLACE_TOL
                                                      else "along the tube: the secondary's central screw")))})
    step("primary", 3, _t("primario, il riflesso del secondario con il collimatore", "the primary, the secondary's reflection with the collimator"), sh,
         _t("viti del primario (o la camera inclinata nel focheggiatore: la prova di rotazione lo dice)", "the primary's screws (or the camera tilted in the focuser: the rotation test tells)"))
    out.append({"code": "spot_hidden", "ok": None,
                "text": _t("il salvabuchi è nascosto dal riflesso del secondario: il passo 3 usa quel riflesso sull'asse", "the centre spot is hidden by the secondary's reflection: step 3 uses that reflection on the axis")})
    return out


def verdict(o: dict) -> list[dict]:
    from .ast_stars import way
    if o.get("view") == "live":
        return _live(o)
    sec, out = o["secondary"], []
    d = o.get("drawtube")
    # 1) the secondary's tilt: the centre spot on the focuser's axis (the drawtube's centre)
    if d and "spot" in o:
        sp = o["spot"]
        off = math.hypot(sp["x"] - d["x"], sp["y"] - d["y"]) / sec["r"]
        ok = off <= SPOT_OK
        out.append({"code": "secondary_tilt", "ok": ok,
                    "text": _t(("1) inclinazione del secondario: il salvabuchi è al centro del drawtube "
                             f"(scarto {off:.1%} del raggio del secondario)" if ok else
                             f"1) inclinazione del secondario: il salvabuchi è spostato verso "
                             f"{way(round(math.degrees(math.atan2(sp['y'] - d['y'], sp['x'] - d['x']))))} di {off:.1%} "
                             "del raggio del secondario rispetto al centro del drawtube — le 3 viti del secondario"), ("1) the secondary's tilt: the centre spot is at the centre of the drawtube "
                             f"({off:.1%} of the secondary's radius off)" if ok else
                             f"1) the secondary's tilt: the centre spot is off towards "
                             f"{way(round(math.degrees(math.atan2(sp['y'] - d['y'], sp['x'] - d['x']))))} by {off:.1%} "
                             "of the secondary's radius from the centre of the drawtube — the secondary's 3 screws"))})
    err = sec["round_err"] or 0.0
    if sec["round"] >= ROUND_OK - 2 * err:
        out.append({"code": "secondary_round", "ok": True,
                    "text": _t(f"2) secondario rotondo: assi al {sec['round']:.1%} uno dell'altro (±{err:.2%})", f"2) the secondary is round: its axes at {sec['round']:.1%} of each other (±{err:.2%})")})
    else:
        out.append({"code": "secondary_oval", "ok": False,
                    "text": _t(f"2) secondario ovale: assi al {sec['round']:.1%} uno dell'altro — rotazione o inclinazione del "
                            "secondario da ritoccare", f"2) the secondary is oval: its axes at {sec['round']:.1%} of each other — the secondary's rotation or "
                            "tilt needs a touch")})
    if d and o.get("expected"):
        e = o["expected"]
        top = max(abs(e["lo"]), abs(e["hi"])) + PLACE_TOL
        ok = e["across"] <= PLACE_TOL and e["along"] <= top
        out.append({"code": "secondary_place", "ok": ok,
                    "text": _t((f"2) posizione del secondario: il contorno è dove l'offset lo mette — {e['along']:.1%} del "
                             f"suo raggio lungo il tubo (atteso fino a {top:.0%}, il collimatore a circa {e['view_mm']} mm), "
                             f"{e['across']:.1%} di traverso" if ok else
                             f"2) posizione del secondario: il contorno è {e['along']:.1%} lungo il tubo (atteso fino a "
                             f"{top:.0%}) e {e['across']:.1%} di traverso — "
                             + ("di traverso: rotazione del secondario" if e["across"] > PLACE_TOL else
                                "lungo il tubo: il secondario va avvicinato o allontanato dal primario (vite centrale)")), (f"2) the secondary's place: the outline is where the offset puts it — {e['along']:.1%} of "
                             f"its radius along the tube (expected up to {top:.0%}, the collimator at about {e['view_mm']} mm), "
                             f"{e['across']:.1%} across" if ok else
                             f"2) the secondary's place: the outline is {e['along']:.1%} along the tube (expected up to "
                             f"{top:.0%}) and {e['across']:.1%} across — "
                             + ("across: the secondary's rotation" if e["across"] > PLACE_TOL else
                                "along the tube: the secondary is to be moved closer to or away from the primary (central screw)")))})
    elif d:
        out.append({"code": "secondary_place", "ok": None,
                    "text": _t(f"2) posizione del secondario: il contorno è a {d['off']:.1%} del raggio del drawtube dal centro "
                            "— con l'offset non deve essere centrato; quanto spostato si calcola con le misure del tubo "
                            "(diametro del secondario, apertura, focale)", f"2) the secondary's place: the outline is {d['off']:.1%} of the drawtube's radius from the centre "
                            "— with the offset it must not be centred; how far off is worked out from the tube's measures "
                            "(the secondary's diameter, aperture, focal length)")})
    else:
        out.append({"code": "drawtube_unseen", "ok": None,
                    "text": _t("il bordo del drawtube non è intero nella foto: la posizione del secondario non si giudica", "the drawtube's edge is not whole in the picture: the secondary's place cannot be judged")})
    if "spot" in o:
        sp = o["spot"]
        ok = sp["off"] <= SPOT_OK
        pm = _t(f" (±{sp['spread'] / 2:.1%} fra le misure)", f" (±{sp['spread'] / 2:.1%} between the measures)") if sp.get("spread") is not None else ""
        out.append({"code": "primary", "ok": ok,
                    "text": _t((f"3) primario: il salvabuchi è nel riflesso del collimatore, scarto {sp['off']:.1%} del raggio "
                             f"del secondario{pm} — entro quello che una foto può vedere; il giudice finale sono le stelle"
                             if ok else
                             f"3) primario: il salvabuchi è spostato verso {way(sp['toward_deg'])} di {sp['off']:.1%} del "
                             "raggio del secondario rispetto al riflesso del collimatore — viti del primario"), (f"3) the primary: the centre spot is in the collimator's reflection, {sp['off']:.1%} of the secondary's "
                             f"radius off{pm} — within what a picture can see; the stars are the final judge"
                             if ok else
                             f"3) the primary: the centre spot is off towards {way(sp['toward_deg'])} by {sp['off']:.1%} of the "
                             "secondary's radius from the collimator's reflection — the primary's screws"))})
    else:
        out.append({"code": "spot_unseen", "ok": None, "text": _t("non trovo il salvabuchi nel riflesso del collimatore", "I cannot find the centre spot in the collimator's reflection")})
    out.append({"code": "shadow", "ok": None,
                "text": _t("l'ombra del secondario non si giudica: con il secondario decentrato di un Newton veloce appare "
                        "spostata, ed è giusto", "the secondary's shadow is not judged: with the offset secondary of a fast Newtonian it looks "
                        "off, and rightly so")})
    return out
