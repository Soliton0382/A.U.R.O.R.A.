# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🌌 The whole deep sky to choose from (ROADMAP N30; owner, 17 Oct: «che Aurora non sia legata ai miei dataset per le
riprese ma che abbia accesso a tutto il catalogo astronomico»): public catalogues fetched on first use, never shipped
with the code, kept in the person's astro folder (sky_catalog.json) and fetched again after REFRESH_DAYS.

| source                         | what                                      | licence / where                         |
|--------------------------------|-------------------------------------------|-----------------------------------------|
| OpenNGC (NGC, IC, addendum)    | galaxies, nebulae, clusters, Messier names | CC-BY-SA 4.0, github.com/mattiaverga     |
| Sharpless 1959 (VizieR VII/20) | the HII regions: narrowband                | CDS VizieR                              |
| Barnard 1927 (VII/220A)        | dark nebulae                               | CDS VizieR                              |
| Lynds 1962 (VII/7A)            | dark nebulae, the darkest (opacity ≥ 5)    | CDS VizieR                              |

Kept: what a camera can take (galaxies to V 13.5 and 1′; every nebula; clusters to mag 10); duplicates and single
stars left out; a Sharpless region that is an NGC/IC nebula already becomes its alias (Sh2-281 → M42)."""
from __future__ import annotations

import csv
import io
import json
import re
import time
from pathlib import Path

import numpy as np

FILE = "sky_catalog.json"
REFRESH_DAYS = 180
OPENNGC = "https://raw.githubusercontent.com/mattiaverga/OpenNGC/HEAD/database_files/"
VIZIER = "https://vizier.cds.unistra.fr/viz-bin/asu-tsv"
UA = {"User-Agent": "A.U.R.O.R.A. sky catalogue (github.com/Soliton0382/A.U.R.O.R.A.)"}
GALAXY = ("G", "GPair", "GTrpl", "GGroup")
EMISSION = ("HII", "EmN", "SNR", "PN", "Cl+N")
KEEP = GALAXY + EMISSION + ("RfN", "Neb", "DrkN", "OCl", "GCl")
GALAXY_MAG, GALAXY_MIN_ARCMIN, CLUSTER_MAG, LDN_OPACITY = 13.5, 1.0, 10.0, 5
# kind → the imaging class of ast_sensor (the bright cores, HDR, are told by name there)
CLASS = {**{t: "broadband" for t in GALAXY + ("RfN", "DrkN", "OCl", "GCl")}, **{t: "narrowband" for t in EMISSION},
         "Neb": "narrowband"}
WORDS = {"G": "galassia", "GPair": "coppia di galassie", "GTrpl": "tripletta di galassie", "GGroup": "gruppo di galassie",
         "HII": "regione HII", "EmN": "nebulosa a emissione", "SNR": "resto di supernova", "PN": "nebulosa planetaria",
         "Cl+N": "ammasso con nebulosa", "RfN": "nebulosa a riflessione", "Neb": "nebulosa", "DrkN": "nebulosa oscura",
         "OCl": "ammasso aperto", "GCl": "ammasso globulare"}


def _f(x: str) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _hms(x: str, hours: bool) -> float | None:
    m = re.match(r"([+-]?)(\d+):(\d+):([\d.]+)", x or "")
    if not m:
        return None
    v = int(m.group(2)) + int(m.group(3)) / 60 + float(m.group(4)) / 3600
    v = -v if m.group(1) == "-" else v
    return v * 15 if hours else v


def _ngc_name(raw: str) -> str:
    """OpenNGC's names as they are said: NGC0224 → NGC 224, B033 → B33, C009 → Caldwell 9, Cl399 → Collinder 399."""
    m = re.match(r"(NGC|IC)0*(\d+)(.*)", raw)
    if m:
        return f"{m.group(1)} {m.group(2)}{m.group(3)}"
    m = re.match(r"(B|C|Cl)0*(\d+)$", raw)
    return {"B": "B{}", "C": "Caldwell {}", "Cl": "Collinder {}"}[m.group(1)].format(m.group(2)) if m else raw


# the names amateurs use in Italian (and some English ones OpenNGC does not carry), by the catalogue's own name
ITALIAN = {"M1": "Granchio", "M8": "Laguna", "M16": "Aquila", "M17": "Omega,Cigno", "M20": "Trifida", "M27": "Manubrio",
           "M31": "Andromeda", "M33": "Triangolo", "M42": "Orione,Grande Nebulosa di Orione", "M45": "Pleiadi",
           "M51": "Vortice", "M57": "Anello", "M63": "Girasole", "M81": "Bode", "M82": "Sigaro", "M101": "Girandola",
           "M104": "Sombrero", "NGC 7000": "Nord America", "IC 5070": "Pellicano", "IC 1805": "Cuore,Heart",
           "IC 1848": "Anima,Soul", "B33": "Testa di Cavallo", "NGC 2024": "Fiamma", "NGC 6960": "Velo dell'Ovest,Western Veil",
           "NGC 6992": "Velo dell'Est,Eastern Veil", "NGC 2237": "Rosetta,Rosette", "NGC 2264": "Cono,Albero di Natale",
           "IC 1396": "Proboscide d'Elefante,Elephant's Trunk", "NGC 7635": "Bolla,Bubble", "NGC 6888": "Crescente,Crescent",
           "NGC 7023": "Iris", "NGC 1499": "California", "IC 410": "Girino,Tadpoles", "IC 2118": "Testa di Strega,Witch Head",
           "IC 63": "Fantasma di Cassiopea,Ghost of Cassiopeia", "NGC 281": "Pac-Man", "IC 5146": "Bozzolo,Cocoon",
           "NGC 6543": "Occhio di Gatto,Cat's Eye", "NGC 2392": "Eschimese,Eskimo", "NGC 869": "Doppio Ammasso,Double Cluster",
           "NGC 7293": "Elica,Helix", "NGC 2175": "Testa di Scimmia,Monkey Head", "IC 434": "Testa di Cavallo (regione)",
           "NGC 1333": "Embrione,Embryo", "Sh2-240": "Simeis 147,Spaghetti", "NGC 6820": "Sh2-86", "IC 1795": "Pesce,Fish Head"}


def openngc(text: str) -> list[dict]:
    """The rows of OpenNGC's NGC.csv / addendum.csv a camera can take (pure: tested on made-up rows)."""
    out = []
    for r in csv.DictReader(io.StringIO(text), delimiter=";"):
        kind = r.get("Type", "")
        if kind not in KEEP:
            continue
        ra, dec = _hms(r.get("RA", ""), True), _hms(r.get("Dec", ""), False)
        if ra is None or dec is None:
            continue
        maj, mn = _f(r.get("MajAx")), _f(r.get("MinAx"))
        mag = _f(r.get("V-Mag")) or _f(r.get("B-Mag"))
        if kind in GALAXY and (mag is None or mag > GALAXY_MAG or (maj or 0) < GALAXY_MIN_ARCMIN):
            continue
        if kind in ("OCl", "GCl") and (mag is None or mag > CLUSTER_MAG):
            continue
        name, aliases = _ngc_name(r["Name"]), []
        if r.get("M"):
            aliases, name = [name], f"M{int(r['M'])}"
        common = [c.strip() for c in (r.get("Common names") or "").split(",") if c.strip()]
        out.append({"name": name, "aliases": aliases, "common": common[:3], "type": kind, "ra": round(ra, 4),
                    "dec": round(dec, 4), "maj": maj, "min": mn or maj, "pa": _f(r.get("PosAng")), "mag": mag,
                    "sb": _f(r.get("SurfBr"))})
    return out


def _tsv(text: str) -> list[dict]:
    """VizieR's asu-tsv: comments, a header, a units line and a dashes line, then the rows."""
    lines = [x for x in text.splitlines() if x and not x.startswith("#")]
    if len(lines) < 3:
        return []
    head = [h.strip() for h in lines[0].split("\t")]
    return [dict(zip(head, (v.strip() for v in x.split("\t")))) for x in lines[3:]]


def sharpless(text: str) -> list[dict]:
    return [{"name": f"Sh2-{int(r['Sh2'])}", "aliases": [], "common": [], "type": "HII", "ra": round(float(r["_RAJ2000"]), 4),
             "dec": round(float(r["_DEJ2000"]), 4), "maj": _f(r.get("Diam")), "min": _f(r.get("Diam")), "pa": None,
             "mag": None, "sb": None, "bright": _f(r.get("Bright"))} for r in _tsv(text) if r.get("Sh2")]


def barnard(text: str) -> list[dict]:
    return [{"name": f"B{r['Barn'].strip()}", "aliases": [], "common": [], "type": "DrkN", "ra": round(float(r["_RAJ2000"]), 4),
             "dec": round(float(r["_DEJ2000"]), 4), "maj": _f(r.get("Diam")), "min": _f(r.get("Diam")), "pa": None,
             "mag": None, "sb": None} for r in _tsv(text) if r.get("Barn")]


def lynds(text: str) -> list[dict]:
    out = []
    for r in _tsv(text):
        area, op = _f(r.get("Area")), _f(r.get("Opacity"))
        if not r.get("LDN") or area is None or (op or 0) < LDN_OPACITY:
            continue
        d = round(2 * (area / np.pi) ** 0.5 * 60, 1)            # the diameter of a disc of that area, arcmin
        out.append({"name": f"LDN {int(r['LDN'])}", "aliases": [], "common": [], "type": "DrkN",
                    "ra": round(float(r["_RAJ2000"]), 4), "dec": round(float(r["_DEJ2000"]), 4), "maj": d, "min": d,
                    "pa": None, "mag": None, "sb": None, "opacity": op})
    return out


def merge(base: list[dict], extra: list[dict], within_arcmin: float = 10.0) -> list[dict]:
    """`extra` added to `base`; one already there (the same kind of thing within `within_arcmin`, or within its own
    size) becomes an alias of it instead."""
    if not base:
        return base + extra
    ra, dec = np.radians([o["ra"] for o in base]), np.radians([o["dec"] for o in base])
    out = list(base)
    for e in extra:
        a, d = np.radians(e["ra"]), np.radians(e["dec"])
        sep = np.degrees(np.arccos(np.clip(np.sin(dec) * np.sin(d) + np.cos(dec) * np.cos(d) * np.cos(ra - a), -1, 1))) * 60
        near = np.flatnonzero(sep < max(within_arcmin, (e.get("maj") or 0) / 2))
        same = [i for i in near if CLASS.get(base[i]["type"]) == CLASS.get(e["type"])]
        if same:
            i = min(same, key=lambda k: sep[k])
            if e["name"] != out[i]["name"]:
                out[i] = {**out[i], "aliases": out[i]["aliases"] + [e["name"]]}
        else:
            out.append(e)
    return out


def _get(url: str, params: dict | None = None) -> str:
    import httpx
    r = httpx.get(url, params=params, headers=UA, timeout=120, follow_redirects=True)
    r.raise_for_status()
    return r.text


def _vizier(source: str, cols: str) -> str:
    return _get(VIZIER, {"-source": source, "-out.max": "unlimited", "-out.add": "_RAJ2000,_DEJ2000", "-out": cols})


def fetch() -> dict:
    """Every source, fetched now (network): {"made", "sources": {name: count or error}, "objects"}."""
    objs, sources = [], {}
    for name, fn in (("OpenNGC", lambda: openngc(_get(OPENNGC + "NGC.csv")) + openngc(_get(OPENNGC + "addendum.csv"))),
                     ("Sharpless", lambda: sharpless(_vizier("VII/20/catalog", "Sh2,Diam,Bright"))),
                     ("Barnard", lambda: barnard(_vizier("VII/220A/barnard", "Barn,Diam"))),
                     ("Lynds", lambda: lynds(_vizier("VII/7A/ldn", "LDN,Area,Opacity")))):
        try:
            got = fn()
            objs = got if name == "OpenNGC" else merge(objs, got)
            sources[name] = len(got)
        except Exception as e:                       # noqa: BLE001 — one source down: the others still count
            sources[name] = f"non scaricato: {type(e).__name__}: {str(e)[:120]}"
    return {"made": time.time(), "sources": sources, "objects": objs}


def load(folder: Path, refresh: bool = False) -> dict:
    """The catalogue of the folder, fetched when missing, older than REFRESH_DAYS, or asked; the old one kept when the
    network fails."""
    f = folder / FILE
    old = None
    try:
        old = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    if old and not refresh and time.time() - old.get("made", 0) < REFRESH_DAYS * 86400:
        return old
    new = fetch()
    if not new["objects"] or (old and len(new["objects"]) < 0.8 * len(old.get("objects", []))):
        return old or new                            # a partial download never replaces a whole catalogue
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(new, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(f)
    return new


def find(objects: list[dict], text: str) -> dict | None:
    """An object by its name, an alias or a common name («M 42», «ngc7000», «Nebulosa Nord America» → its English name
    is not known: «North America»)."""
    want = re.sub(r"[\W_]+", "", text.strip().lower())          # «Velo dell Ovest» = «Velo dell'Ovest»
    if not want:
        return None
    key = lambda s: re.sub(r"[\W_]+", "", s.lower())                    # noqa: E731
    for o in objects:
        if key(o["name"]) == want or any(key(a) == want for a in o["aliases"]):
            return o
    hits = [o for o in objects if any(want in key(c) for c in o["common"] + named(o))]
    return min(hits, key=lambda o: len((o["common"] + named(o))[0])) if hits else None


def named(o: dict) -> list[str]:
    """The Italian (and missing English) names of an object."""
    return [n for k in [o["name"]] + o["aliases"] for n in ITALIAN.get(k, "").split(",") if n]
