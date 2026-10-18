# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔭 A sequence for N.I.N.A. written from the person's own (ROADMAP N29 phase 2, step 1; owner, 19 Oct: «costruisci la
sequenza per N.I.N.A.… usiamo come base "…" per l-eXtreme e "…" per idas lps d2»). The template of the target's kind
(astro_setup.json "templates": {"narrowband": file, "broadband": file}, files of the astro folder's sequences/) is
read and only these change: the target (name, J2000 coordinates of every slew and centring), the exposure, gain,
offset and count, the dither's interval, the cooling. Everything else — the filter, guiding, autofocus, the flip, the
start and the end — stays as the person built it in N.I.N.A.

Without a rotator (owner, 19 Oct: «non ho più il rotatore»): the rotator's instructions are taken out (SolveAndRotate;
CenterAndRotate becomes Center; a message about the rotator), the position angle set to 0, and a mosaic template
keeps its first panel only, made the target. What was taken out is said. The progress N.I.N.A. keeps in a sequence
(the frames taken, the loops done) is set back to zero. The file is checked as any sequence is (ast_sequence: the
darks, the cooling, guiding, flip) and written next to the templates as «<target> Aurora.json»; never loaded into
N.I.N.A. here — the person opens it."""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from . import ast_sequence

OUT_SUFFIX = " Aurora"
ROTATOR = ("SolveAndRotate", "MoveRotator", "RotatorMove", "ReverseRotator")


def _kind(n: dict) -> str:
    return ast_sequence._kind(n)


def _children(n: dict) -> list[dict]:
    items = n.get("Items")
    return items.get("$values", []) if isinstance(items, dict) else []


def _walk(n, parent=None, out=None) -> list[tuple[dict, dict | None]]:
    """(node, the list holding it) for every node with a type, Parent links left out."""
    out = [] if out is None else out
    if isinstance(n, dict):
        if n.get("$type"):
            out.append((n, parent))
        for k, v in n.items():
            if k == "Parent":
                continue
            if isinstance(v, dict) and isinstance(v.get("$values"), list):
                for x in v["$values"]:
                    _walk(x, v["$values"], out)
            elif isinstance(v, (dict, list)):
                _walk(v, None, out)
    elif isinstance(n, list):
        for x in n:
            _walk(x, n, out)
    return out


def _has_exposure(n: dict) -> bool:
    return any(_kind(x) == "TakeExposure" for x, _ in _walk(n))


def coords(ra_deg: float, dec_deg: float) -> dict:
    """N.I.N.A.'s InputCoordinates (J2000), its own field types."""
    h = (ra_deg % 360) / 15
    rh, rm = int(h), int((h - int(h)) * 60)
    rs = round((h - rh - rm / 60) * 3600, 5)
    a = abs(dec_deg)
    dd, dm = int(a), int((a - int(a)) * 60)
    ds = round((a - dd - dm / 60) * 3600, 5)
    return {"RAHours": rh, "RAMinutes": rm, "RASeconds": rs, "NegativeDec": dec_deg < 0,
            "DecDegrees": -dd if dec_deg < 0 else dd, "DecMinutes": dm, "DecSeconds": ds}


def _set_coords(node: dict, key: str, c: dict) -> None:
    old = node.get(key)
    if isinstance(old, dict):
        old.update(c)


def build(template: dict, target: dict, exposure_s: float, count: int, gain: float, offset: float,
          dither_every: int | None = None, cool_c: float | None = None) -> tuple[dict, list[str]]:
    """(the new sequence, what was taken out or changed beyond the target and the exposures, in words)."""
    seq = copy.deepcopy(template)
    notes: list[str] = []
    name = str(target["name"]).strip()[:80]
    c = coords(float(target["ra_deg"]), float(target["dec_deg"]))
    nodes = _walk(seq)
    leaves = [n for n, _ in nodes if _kind(n) == "DeepSkyObjectContainer" and _has_exposure(n)
              and not any(_kind(x) == "DeepSkyObjectContainer" and x is not n for x, _ in _walk(n))]
    if not leaves:
        raise ValueError("il modello non ha un bersaglio con delle pose (DeepSkyObjectContainer con TakeExposure)")
    for extra in leaves[1:]:                           # a mosaic without a rotator: its first panel only
        holder = next(p for n, p in nodes if n is extra)
        holder.remove(extra)
    if len(leaves) > 1:
        notes.append(f"mosaico di {len(leaves)} pannelli ridotto al primo (senza rotatore)")
    for n, holder in _walk(seq):
        k = _kind(n)
        if holder is None or not any(x is n for x in holder):
            holder = None                              # already gone with what held it
        if any(k.startswith(r) for r in ROTATOR) and holder is not None:
            holder.remove(n)
            notes.append(f"tolto {k}")
        elif k == "MessageBox" and re.search(r"rotat", str(n.get("Text", "")), re.I) and holder is not None:
            holder.remove(n)
            notes.append(f"tolto il messaggio «{n.get('Text')}»")
        elif k == "CenterAndRotate":
            n["$type"] = n["$type"].replace("CenterAndRotate", "Center")
            n.pop("PositionAngle", None)
            notes.append("CenterAndRotate diventato Center")
    for n, _ in _walk(seq):
        k = _kind(n)
        if k == "SequenceRootContainer":
            n["Name"] = name
        elif k == "DeepSkyObjectContainer":
            n["Name"] = name
            t = n.get("Target") or {}
            t["TargetName"] = name
            if "PositionAngle" in t:
                t["PositionAngle"] = 0.0
            _set_coords(t, "InputCoordinates", c)
            if isinstance(n.get("ExposureInfoList"), dict):
                n["ExposureInfoList"]["$values"] = []
        elif isinstance(n.get("Coordinates"), dict):
            _set_coords(n, "Coordinates", c)
        if k == "TakeExposure" and str(n.get("ImageType", "LIGHT")).upper() == "LIGHT":
            n.update(ExposureTime=float(exposure_s), Gain=int(gain), Offset=int(offset))
        elif k == "LoopCondition" and _kind_up(seq, n) == "TakeManyExposures":
            n.update(Iterations=int(count), CompletedIterations=0)
        elif k == "DitherAfterExposures" and dither_every:
            n["AfterExposures"] = int(dither_every)
        elif k == "CoolCamera" and cool_c is not None:
            n["Temperature"] = float(cool_c)
        elif k == "SequentialContainer" and re.search(r"\s*(and|&|e)\s+rotate\b", str(n.get("Name") or ""), re.I):
            n["Name"] = re.sub(r"\s*(and|&|e)\s+rotate\b", " and center", n["Name"], flags=re.I)
        elif k == "SequentialContainer" and re.fullmatch(r"\d+\s*x\s*\d+\s*s", str(n.get("Name") or "")):
            n["Name"] = f"{int(count)}x{exposure_s:g}s"
        if "CompletedIterations" in n:
            n["CompletedIterations"] = 0
    _check_refs(seq)
    return seq, notes


def _kind_up(seq: dict, cond: dict) -> str:
    """The kind of the node whose Conditions hold this condition."""
    for n, _ in _walk(seq):
        conds = n.get("Conditions")
        if isinstance(conds, dict) and any(x is cond for x in conds.get("$values", [])):
            return _kind(n)
    return ""


def _check_refs(seq: dict) -> None:
    text = json.dumps(seq)
    ids = set(re.findall(r'"\$id": "(\d+)"', text))
    if missing := set(re.findall(r'"\$ref": "(\d+)"', text)) - ids:
        raise ValueError(f"la sequenza rimanda a nodi tolti ({', '.join(sorted(missing, key=int)[:5])}): non scritta")


def template_for(folder: Path, kind: str, templates: dict) -> Path:
    name = templates.get(kind) or templates.get("broadband" if kind in ("hdr", "galaxy") else "")
    if not name:
        raise ValueError(f"nessun modello per «{kind}»: indica in astro_setup.json \"templates\" quale sequenza usare "
                         "(per esempio {\"narrowband\": \"...json\", \"broadband\": \"...json\"})")
    f = folder / "sequences" / name
    if not f.is_file():
        raise ValueError(f"il modello «{name}» non è nella cartella sequences/")
    return f


def write(folder: Path, kind: str, templates: dict, target: dict, exposure_s: float, count: int, gain: float,
          offset: float, rig: dict, darks: list[dict], dither_every: int | None = None,
          cool_c: float | None = None) -> dict:
    """The sequence written next to the templates: {file, template, notes, sequence (read back), checks}."""
    if not 1 <= int(count) <= 2000 or not 0 < float(exposure_s) <= 3600:
        raise ValueError("pose: da 1 a 2000, da 0 a 3600 s")
    src = template_for(folder, kind, templates)
    seq, notes = build(json.loads(src.read_text(encoding="utf-8-sig")), target, exposure_s, count, gain, offset,
                       dither_every, cool_c)
    safe = re.sub(r"[^\w .()+-]", "", str(target["name"])).strip() or "target"
    out = folder / "sequences" / f"{safe}{OUT_SUFFIX}.json"
    if out.resolve() == src.resolve():
        raise ValueError("il file nuovo avrebbe il nome del modello: non lo sovrascrivo")
    text = json.dumps(seq, ensure_ascii=False, indent=2)
    back = ast_sequence.parse(text, out.stem)
    out.write_text(text, encoding="utf-8")
    return {"file": out.name, "template": src.name, "notes": notes, "sequence": back, "count": int(count),
            "checks": ast_sequence.check(back, rig, darks)}


def for_tonight(cfg, name: str, date: str = "", kind: str = "", count: int = 0, exposure_s: float = 0,
                min_alt: float = 30) -> dict:
    """The person's sequence for one object and night: the object's J2000 place from the catalogue, its kind and usable
    hours from tonight's plan, the camera's set for that kind measured on their frames (with their darks), the count
    that fills the usable hours (each frame's cost besides its light included) unless given."""
    from . import ast_advice, ast_catalog, ast_inventory, ast_sensor, ast_skyplan
    folder = ast_inventory.folder(cfg)
    profile = ast_inventory.profile(cfg) or {}
    saved = ast_advice.setup(folder)
    o = ast_catalog.find(ast_catalog.load(folder)["objects"], name)
    if not o:
        raise ValueError(f"«{name}» non è nel catalogo: prova il nome NGC/IC/M/Sh2")
    p = ast_skyplan.plan(cfg, profile, folder, date, min_alt, "", 1, name=name, saved=saved.get("kinds") or {})
    row = (p.get("targets") or [{}])[0]
    kind = kind or row.get("kind") or "broadband"
    notes = []
    if kind == "hdr":
        notes.append("oggetto da HDR: per ora una sola posa, quella della banda larga")
    lib = ast_inventory.darks_library(cfg)["darks"]
    tpl_name = (saved.get("templates") or {}).get("narrowband" if kind == "narrowband" else "broadband")
    every = None
    if tpl_name and (folder / "sequences" / tpl_name).is_file():
        every = ast_sequence.parse((folder / "sequences" / tpl_name).read_text(encoding="utf-8-sig")).get("dither_every")
    m = ast_sensor.measure(cfg, str(cfg["AURORA_ASTRO_FRAMES_DIR"] or "").strip())
    sp = ast_sensor.plan(m, lib, profile, every)
    k = sp["kinds"].get("narrowband" if kind == "narrowband" else "broadband") or {}
    s = k.get("with_darks") or k.get("best")
    if not s:
        raise ValueError("nessuna impostazione misurata per questo tipo: servono pose di prova nella cartella dei frame")
    if not k.get("with_darks"):
        notes.append("nessun dark adatto: la posa è quella ideale, i dark vanno fatti")
    exp = float(exposure_s or s["exposure_s"])
    hours = float(row.get("hours") or 0)
    if not count:
        count = int(hours * 3600 // (exp + sp["overhead_s"]))
        if count < 1:
            raise ValueError(f"«{o['name']}» non ha ore utili la notte del {p.get('date')} sopra {min_alt:g}°: "
                             "indica tu il numero di pose")
    rig = profile.get("rig") or {}
    out = write(folder, kind, saved.get("templates") or {}, {"name": o["name"], "ra_deg": o["ra"], "dec_deg": o["dec"]},
                exp, count, s["gain"], s["offset"], rig, lib)
    out.update(object=o["name"], common=(ast_catalog.named(o) + o["common"])[:2], kind=kind, date=p.get("date"),
               hours=hours, window=[row.get("from"), row.get("to")], overhead_s=sp["overhead_s"],
               notes=notes + out["notes"])
    return out


def text(r: dict) -> str:
    seq = r["sequence"]
    e = seq["exposures"][0] if seq["exposures"] else {}
    lines = [f"Sequenza scritta: sequences/{r['file']} (dal modello {r['template']}).",
             f"{r['object']}{' — ' + ', '.join(r['common']) if r['common'] else ''}, {r['kind']}, notte del {r['date']}: "
             f"{r['hours']} h utili" + (f" ({r['window'][0]}–{r['window'][1]})" if r["window"][0] else "") + ".",
             f"{seq['targets'][0]['ra_h']:.4f} h, {seq['targets'][0]['dec_deg']:+.3f}° (J2000) · "
             f"{r['count']} pose da {e.get('s'):g} s, gain {e.get('gain'):g}, offset {e.get('offset'):g} · "
             f"dither ogni {seq['dither_every']} · raffreddamento {seq['cool_c']} °C · guida {'sì' if seq['guiding'] else 'no'}"
             f" · autofocus {'sì' if seq['autofocus'] else 'no'} · flip {'sì' if seq['flip'] else 'no'}."]
    if r["notes"]:
        lines.append("Cambiato rispetto al modello: " + "; ".join(r["notes"]) + ".")
    if r["checks"]:
        lines.append("Da controllare: " + "; ".join(f"{c['code']} ({c['level']})" for c in r["checks"]) + ".")
    lines.append("Aprila in N.I.N.A. (Sequenza avanzata → Carica) e controllala prima di avviarla: Aurora non la avvia.")
    return "\n".join(lines)
