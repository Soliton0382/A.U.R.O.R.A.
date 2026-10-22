# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🎨 A project's model seen as it would look built (ROADMAP N42; owner, 23 Oct: «non sarebbe male avere un Proof of
concept che assembla tutto il progetto in una immagine realistica»).

The browser draws the parts' STL (the cad plugin's part_<k>.stl, and exploded_<k>.stl for the exploded view) with a
material each: the one the part was given in cad_build («material»), else one guessed from its name (a coil is copper,
a shaft steel, a support printed plastic). A guess is said to be a guess: the page marks it.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import prj_print, sys_config

# material → its look: base colour (linear 0-1), metallic 0/1, roughness 0-1; copper is the enamelled wire of a coil
# (redder than bare copper, whose own colour looks almost white once on screen)
MATERIALS = {
    "copper": ([0.80, 0.36, 0.16], 1.0, 0.3), "magnet": ([0.66, 0.66, 0.68], 1.0, 0.22),
    "steel": ([0.56, 0.57, 0.58], 1.0, 0.38), "aluminium": ([0.91, 0.92, 0.92], 1.0, 0.42),
    "brass": ([0.91, 0.78, 0.42], 1.0, 0.3), "plastic": ([0.035, 0.037, 0.042], 0.0, 0.5),
    "plastic_light": ([0.82, 0.82, 0.80], 0.0, 0.5), "pcb": ([0.05, 0.28, 0.12], 0.0, 0.45),
    "carbon": ([0.05, 0.05, 0.055], 0.0, 0.3), "rubber": ([0.03, 0.03, 0.03], 0.0, 0.9),
    "glass": ([0.8, 0.88, 0.92], 0.0, 0.05), "wood": ([0.55, 0.36, 0.2], 0.0, 0.7),
}
# words in a part's name (it, en) → material; the first that matches wins
GUESS = [
    (r"bobin|coil|avvolg|winding|spir|rame|copper|filo\b|wire", "copper"),
    (r"magnet|lobo|lobe|sub-polo|polo\b|pole|ndfeb|ferrite", "magnet"),
    (r"albero|shaft|vite|screw|bullon|bolt|dado|nut\b|cuscinett|bearing|perno|pin\b|molla|spring|acciaio|steel", "steel"),
    (r"allumin|alumin|dissipat|heatsink|flang", "aluminium"),
    (r"ottone|brass", "brass"),
    (r"pcb|scheda|board|circuit", "pcb"),
    (r"carbon", "carbon"),
    (r"gomma|rubber|guarniz|gasket|o-ring", "rubber"),
    (r"vetro|glass|lente|lens", "glass"),
    (r"legno|wood", "wood"),
    (r"support|statore|stator|piastra|plate|cassa|case|guscio|shell|telaio|frame|coperch|cover|rotore|rotor|disco|disc", "plastic"),
]


def material(part: dict) -> tuple[str, bool]:
    """A part's material and whether it was guessed from the name."""
    given = str(part.get("material") or "").lower()
    if given in MATERIALS:
        return given, False
    name = str(part.get("name") or "").lower()
    for rx, m in GUESS:
        if re.search(rx, name):
            return m, True
    return "plastic_light", True


def scene(cfg: sys_config.Config, project: str) -> list[dict]:
    """The project's models with each part's material and look, for the realistic view."""
    out = []
    for m in prj_print.models(cfg, project):
        folder = prj_print._folder(cfg, project, m["model"])
        listed = prj_print._listed(folder)
        parts = []
        for k, p in enumerate(listed):
            if not (folder / f"part_{k}.stl").is_file():
                continue
            mat, guessed = material(p)
            parts.append({"k": k, "sign": p.get("sign", k), "name": p.get("name", ""), "material": mat,
                          "guessed": guessed, "exploded": (folder / f"exploded_{k}.stl").is_file()})
        out.append({"model": m["model"], "parts": parts})
    return out


def mesh(cfg: sys_config.Config, project: str, model: str, k: int, exploded: bool = False) -> Path:
    """The STL of one part, where it sits in the assembly or in the exploded view."""
    f = prj_print._folder(cfg, project, model) / f"{'exploded' if exploded else 'part'}_{int(k)}.stl"
    if not f.is_file():
        raise FileNotFoundError("no such part")
    return f
