# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🖨️ A project's models for a 3D printer (ROADMAP N41; owner, 23 Oct: «non sarebbe male avere un "esporta per
stampante 3d" così si creano i file da inviare ad una stampante 3d»).

The cad plugin (cad_build) writes every part of a model as STL into <project>/cad/<model>/ (part_<k>.stl, in the
order of parts.json). Here they are gathered into one zip: a file per part, named by its sign and name, and a README
with the list, the sizes in mm and generic printing advice, said to be advice and not a calculation for that part.
Each part is laid on its largest flat face and the parts are set on a bed of the printer's size (prj_print_flat):
one STL per part and one 3MF with the whole plate, in millimetres; the README says what does not fit.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path

from . import prj_policy, sys_config

README = {
    "it": {"head": "{project} — {model}: file per la stampante 3D",
           "units": "Unità: millimetri. Un file STL per parte, già appoggiata sulla sua faccia piana più grande; "
                    "piatto_1.3mf (e i seguenti) hanno le parti disposte su piatti di {bed} mm: aprili nello slicer "
                    "così come sono. Controlla l'orientamento dei pezzi con sbalzi: la faccia più grande non è sempre "
                    "la migliore.",
           "big": "ATTENZIONE: più grandi del piatto di {bed} mm: {names}.",
           "over": "Tutte insieme non stanno su un piatto di {bed} mm: sono divise in {n} piatti, uno per file.",
           "parts": "Parti ({n}):", "row": "- {file}: segno {sign}, {name}, {size} mm, quantità 1",
           "advice": "CONSIGLIO GENERICO, non un calcolo per questi pezzi: PLA o PETG, ugello 0,4 mm, strato 0,2 mm, "
                     "3 perimetri, riempimento 20-30 %; per pezzi caldi o sotto carico PETG o ASA e riempimento più "
                     "alto. Verifica le misure e le tolleranze di accoppiamento con una prova."},
    "en": {"head": "{project} — {model}: files for the 3D printer",
           "units": "Units: millimetres. One STL file per part, already resting on its largest flat face; "
                    "piatto_1.3mf (and the next ones) have the parts set on {bed} mm beds: open them in the slicer as "
                    "they are. Check the parts with overhangs: the largest face is not always the best.",
           "big": "WARNING: larger than the {bed} mm bed: {names}.",
           "over": "All together they do not fit one {bed} mm bed: they are split over {n} beds, one file each.",
           "parts": "Parts ({n}):", "row": "- {file}: sign {sign}, {name}, {size} mm, quantity 1",
           "advice": "GENERIC ADVICE, not a calculation for these parts: PLA or PETG, 0.4 mm nozzle, 0.2 mm layers, "
                     "3 perimeters, 20-30 % infill; for hot or loaded parts PETG or ASA and more infill. Check the "
                     "sizes and the fits with a test print."},
}


def _folder(cfg: sys_config.Config, project: str, model: str | None = None) -> Path:
    for v in (project, model) if model is not None else (project,):
        if not prj_policy.NAME.fullmatch(v or ""):
            raise ValueError("bad name")
    p = cfg.path("AURORA_PROJECTS_DIR") / project
    if not p.is_dir():
        raise ValueError("no such project")
    return p / "cad" if model is None else p / "cad" / model


def _listed(folder: Path) -> list[dict]:
    """parts.json's parts, in the order of part_<k>.stl."""
    try:
        listed = json.loads((folder / "parts.json").read_text(encoding="utf-8")).get("parts", [])
    except (OSError, ValueError):
        return []
    return [p if isinstance(p, dict) else {} for p in listed] if isinstance(listed, list) else []   # k stays k


def _parts(folder: Path) -> list[dict]:
    """The parts that have their STL, with the file they will have in the zip."""
    out = []
    for k, p in enumerate(_listed(folder)):
        stl = folder / f"part_{k}.stl"
        if not stl.is_file():
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", str(p.get("name", "")).lower()).strip("-")[:40] or f"part-{k}"
        out.append({"sign": p.get("sign", k), "name": p.get("name", ""), "size_mm": p.get("size_mm"),
                    "stl": stl, "file": f"{int(p.get('sign', k)):03d}_{slug}.stl"})
    return out


def models(cfg: sys_config.Config, project: str) -> list[dict]:
    """The project's models that can be printed: name and parts (sign, name, size in mm)."""
    cad = _folder(cfg, project)
    if not cad.is_dir():
        return []
    out = []
    for d in sorted(x for x in cad.iterdir() if x.is_dir() and prj_policy.NAME.fullmatch(x.name)):
        parts = _parts(d)
        if parts:
            out.append({"model": d.name, "parts": [{k: p[k] for k in ("sign", "name", "size_mm", "file")} for p in parts]})
    return out


def bundle(cfg: sys_config.Config, project: str, model: str, lang: str = "it",
           bed: tuple[float, float] = (220, 220)) -> bytes:
    """The zip for the printer: the parts' STL laid flat, one 3MF per bed, README.txt."""
    from . import prj_cover_cad, prj_print_flat as F
    folder = _folder(cfg, project, model)
    parts = _parts(folder) if folder.is_dir() else []
    if not parts:
        raise FileNotFoundError("no printable parts")
    words = README["it" if str(lang).startswith("it") else "en"]
    flat = [F.lay_flat(prj_cover_cad.load_stl(p["stl"])) for p in parts]
    placed, plate, big = F.arrange(flat, bed)
    beds = max(plate) + 1
    bed_txt = f"{bed[0]:g} × {bed[1]:g}"
    size = lambda z: " × ".join(f"{v:g}" for v in z) if isinstance(z, list) and len(z) == 3 else "?"
    text = [words["head"].format(project=project, model=model), "", words["units"].format(bed=bed_txt), ""]
    if big:
        text += [words["big"].format(bed=bed_txt, names=", ".join(parts[i]["file"] for i in big)), ""]
    if beds > 1:
        text += [words["over"].format(bed=bed_txt, n=beds), ""]
    text += [words["parts"].format(n=len(parts)),
             *(words["row"].format(file=p["file"], sign=p["sign"], name=p["name"], size=size(p["size_mm"]))
               for p in parts),
             "", words["advice"], ""]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("README.txt", "\n".join(text))
        for p, tri in zip(parts, flat):
            z.writestr(p["file"], F.stl_bytes(tri, p["name"] or p["file"]))
        for b in range(beds):
            z.writestr(f"piatto_{b + 1}.3mf", F.three_mf([(p["name"] or p["file"], tri)
                                                        for p, tri, k in zip(parts, placed, plate) if k == b]))
    return buf.getvalue()
