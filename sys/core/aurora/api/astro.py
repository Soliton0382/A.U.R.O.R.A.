# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔭 Astro (ROADMAP 79 step 0; owner, 16 Oct: «una parte nel menù chiamata astro… lo script da usare, il comando da
utilizzare e dove si trova il file txt che Aurora deve digerire»): the inventory script to download, the command, the
files of the person's astro folder (inventories, manuals, notes) added and removed, and the equipment's profile read
from the latest inventory (ast_inventory) with the darks' library of this machine. Each person's own folder."""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from .core import auth, cfg, log, me

router = APIRouter()
SCRIPT = Path(__file__).resolve().parents[3] / "plugins" / "astro" / "astro_inventory.ps1"   # sys/plugins/astro
COMMAND = "powershell -ExecutionPolicy Bypass -File .\\astro_inventory.ps1"
NAME = re.compile(r"^[\w .()+-]{1,120}\.(txt|md|pdf|csv|json|xml|log)$", re.I)
MAX_BYTES = 50 * 1024 * 1024
OWN = ("darks.json", "astro_setup.json", "autoguide.jsonl", "sensor.json", "frames.json", "sky_catalog.json",
       "collimation.json")   # Aurora's own: the darks' snapshot, the setup, the tuner's log, the frames' headers


@router.get("/v1/aurora/astro", dependencies=[Depends(auth)])
def astro() -> dict:
    from aurora import ast_inventory as A
    d = A.folder(cfg)
    inv = {f.name for f in A.inventories(cfg)}
    files = [{"name": f.name, "bytes": f.stat().st_size, "inventory": f.name in inv, "modified": f.stat().st_mtime}
             for f in sorted(d.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)
             if f.is_file() and f.name not in OWN]
    p = A.profile(cfg)
    if p:                                     # the guide logs added here count, even when the PC's latest are empty
        from aurora import ast_guidelog as G
        if G.logs(d):
            p = {**p, "checks": [c for c in p["checks"] if c["what"] != A.NO_GUIDE_LOG]}
    try:
        where = str(d.relative_to(cfg.root))
    except ValueError:
        where = str(d)
    return {"profile": p, "text": A.text(p), "files": files, "folder": where, "command": COMMAND,
            "script": SCRIPT.name, "darks_dir": str(cfg["AURORA_ASTRO_DARKS_DIR"] or "")}


@router.get("/v1/aurora/astro/script", dependencies=[Depends(auth)])
def astro_script(as_json: bool = False):
    """The inventory script, to run on the astrophotography PC (read only there); as_json: {name, text}, for the page's
    call() (sent again with its key when the phone wakes up, C199)."""
    if as_json:
        return {"name": SCRIPT.name, "text": SCRIPT.read_text(encoding="utf-8")}
    return FileResponse(SCRIPT, media_type="text/plain", filename=SCRIPT.name)


@router.post("/v1/aurora/astro/files", dependencies=[Depends(auth)])
async def astro_add(request: Request) -> dict:
    """The body is the file; its name in X-File-Name: an inventory (.txt) or a manual, a note (.pdf, .md…)."""
    from aurora import ast_inventory as A
    name = Path(str(request.headers.get("x-file-name", ""))).name
    if not NAME.match(name):
        raise HTTPException(status_code=422, detail="a .txt, .md, .pdf, .csv, .json, .xml or .log file, with a plain name")
    raw = await request.body()
    if not raw or len(raw) > MAX_BYTES:
        raise HTTPException(status_code=422, detail="from 1 byte to 50 MB")
    f = A.folder(cfg) / name
    f.write_bytes(raw)
    log.info("audit: %s added %s to the astro folder (%d bytes)", me(), name, len(raw))
    return {"name": name, "bytes": len(raw), "inventory": raw[:80].decode("utf-8-sig", "replace").startswith(A.HEADER)}


@router.delete("/v1/aurora/astro/files/{name}", dependencies=[Depends(auth)])
def astro_remove(name: str) -> dict:
    from aurora import ast_inventory as A
    f = A.folder(cfg) / Path(name).name
    if not f.is_file():
        raise HTTPException(status_code=404, detail="no such file")
    f.unlink()
    log.info("audit: %s removed %s from the astro folder", me(), f.name)
    return {"removed": f.name}


@router.get("/v1/aurora/astro/nights", dependencies=[Depends(auth)])
def astro_nights() -> dict:
    """The nights already guided (ROADMAP N28): PHD2's guide logs of the astro folder read back, each session's RMS and
    settings, and what Aurora reads in them against the imaging scale and N.I.N.A.'s meridian flip (ast_guidelog)."""
    from aurora import ast_guidelog as G, ast_inventory as A
    rig = (A.profile(cfg) or {}).get("rig") or {}
    return {"nights": G.nights(A.folder(cfg), rig.get("scale_arcsec_px"), rig.get("meridian_flip")),
            "scale": rig.get("scale_arcsec_px"), "flip": rig.get("meridian_flip") or {}}


@router.get("/v1/aurora/astro/advice", dependencies=[Depends(auth)])
def astro_advice() -> dict:
    """The values advised (ROADMAP N28): for each setting of the imaging and guiding programs, what is set, what Aurora
    advises and why, the person's own choice; whether the equipment is sized right; the sequences checked (ast_advice)."""
    from aurora import ast_advice as V
    return V.report(cfg)


@router.put("/v1/aurora/astro/advice", dependencies=[Depends(auth)])
async def astro_advice_set(request: Request) -> dict:
    """The person's facts and own choices, merged into the astro folder's setup; an empty value forgets it."""
    from aurora import ast_advice as V
    body = await request.json()
    try:
        changed = V.save(cfg, body if isinstance(body, dict) else {})
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    log.info("audit: %s changed the astro setup (%s)", me(), ", ".join(changed))
    return V.report(cfg)


def _host() -> tuple[str, int]:
    """The telescope's PC (ast_advice.telescope_host)."""
    from aurora import ast_advice
    return ast_advice.telescope_host(cfg)


@router.get("/v1/aurora/astro/imaging", dependencies=[Depends(auth)])
def astro_imaging(object: str = "") -> dict:
    """The camera and the sky measured from the person's frames, and the settings for each kind of object and for the
    one named (ast_sensor); the objects of their sequences to choose from."""
    from aurora import ast_advice as V, ast_inventory as A, ast_sensor as S, ast_sequence as Q
    d = A.folder(cfg)
    m = S.measure(cfg, str(cfg["AURORA_ASTRO_FRAMES_DIR"] or "").strip())
    seqs = Q.sequences(d) + Q.sequences(d / "sequences")
    every = [q["dither_every"] for q in seqs if q.get("dither_every")]
    names = sorted({t["name"] for q in seqs for t in q.get("targets", []) if t.get("name")})
    kinds = V.setup(d).get("kinds") or {}
    out = S.plan(m, A.darks_library(cfg)["darks"], A.profile(cfg), max(set(every), key=every.count) if every else None,
                 object.strip()[:120], kinds)
    return {**out, "sensors": m.get("sensors", []), "sky": m.get("sky", []), "frames": m.get("frames", 0),
            "kinds_count": m.get("kinds", {}), "errors": m.get("errors", []) + ([m["error"]] if m.get("error") else []),
            "frames_dir": bool(str(cfg["AURORA_ASTRO_FRAMES_DIR"] or "").strip()), "objects": names,
            "object_kinds": {n: S.kind_of(n, kinds) for n in names}}


@router.put("/v1/aurora/astro/imaging", dependencies=[Depends(auth)])
async def astro_imaging_set(request: Request) -> dict:
    """An object's kind as the person says it (narrowband, broadband, hdr; empty: guessed from its name again)."""
    from aurora import ast_advice as V, ast_inventory as A, ast_sensor as S
    body = await request.json()
    name, kind = str(body.get("object", "")).strip()[:120], str(body.get("kind", ""))
    if not name or kind not in S.CLASSES + ("",):
        raise HTTPException(status_code=422, detail=f"object, and kind one of {S.CLASSES}")
    d = A.folder(cfg)
    kinds = dict(V.setup(d).get("kinds") or {})
    if kind:
        kinds[name] = kind
    else:
        kinds.pop(name, None)
    V.save_part(d, "kinds", kinds)
    return astro_imaging(name)


@router.get("/v1/aurora/astro/sky", dependencies=[Depends(auth)])
def astro_sky(date: str = "", object: str = "", kind: str = "", min_alt: float = 30, limit: int = 15) -> dict:
    """🌌 Tonight's plan (ROADMAP N30): the night, the forecast and the catalogue's targets ranked for the person's
    equipment; `object`: that one object's night. The catalogue is fetched on the first ask (ast_catalog)."""
    from aurora import ast_skyplan
    if date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise HTTPException(status_code=422, detail="date: YYYY-MM-DD")
    if kind not in ("", "narrowband", "broadband", "hdr", "galaxy"):
        raise HTTPException(status_code=422, detail="kind: narrowband, broadband, hdr or galaxy")
    from aurora import ast_inventory, ast_skythumb
    out = ast_skyplan.tonight(cfg, date, max(0.0, min(80.0, min_alt)), kind, max(1, min(50, limit)), object.strip()[:80])
    folder = ast_inventory.folder(cfg)
    for r in out.get("targets", []):
        r["thumb"] = ast_skythumb.cached(folder, r["name"])          # opened before: its picture in the row
    return out


@router.get("/v1/aurora/astro/sky/thumb", dependencies=[Depends(auth)])
def astro_sky_thumb(object: str):
    """The object's sky (the CDS's DSS2 survey, asked with its catalogue place) with the person's field drawn."""
    from fastapi.responses import Response
    from aurora import ast_skythumb
    try:
        data = ast_skythumb.for_object(cfg, object.strip()[:80])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=502, detail=f"the sky survey did not answer ({type(e).__name__})") from e
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@router.post("/v1/aurora/astro/sky/sequence", dependencies=[Depends(auth)])
async def astro_sky_sequence(request: Request) -> dict:
    """{object, date?, kind?}: the sequence for N.I.N.A. written for that object and night (ast_seqwrite)."""
    from aurora import ast_seqwrite
    body = await request.json()
    date = str(body.get("date") or "")
    if date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise HTTPException(status_code=422, detail="date: YYYY-MM-DD")
    def num(key, lo, hi):                            # {count?, exposure_s?, gain?, offset?}: the person's own values
        v = body.get(key)
        if v in (None, ""):
            return None
        try:
            v = float(v)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail=f"{key}: a number") from None
        if not lo <= v <= hi:
            raise HTTPException(status_code=422, detail=f"{key}: from {lo} to {hi}")
        return v
    count, exp = num("count", 1, 2000), num("exposure_s", 0.001, 3600)
    gain, offset = num("gain", 0, 10000), num("offset", 0, 10000)
    try:
        r = ast_seqwrite.for_tonight(cfg, str(body.get("object") or "").strip()[:80], date, str(body.get("kind") or ""),
                                     int(count or 0), exp or 0, gain=gain, offset=offset)
    except ValueError as e:
        return {"error": str(e)}
    log.info("audit: %s had a sequence written: %s", me(), r["file"])
    return {"file": r["file"], "text": ast_seqwrite.text(r), "params": r.get("params")}


@router.get("/v1/aurora/astro/sky/sequence/file", dependencies=[Depends(auth)])
def astro_sky_sequence_file(name: str, format: str = "nina", folder: str = ""):
    """A written sequence, downloaded: as written (N.I.N.A.), or for Ekos (folder: where the .esq will be on the Ekos
    machine), CCDciel or as a target list (ast_seqexport)."""
    import json as _json
    from fastapi.responses import Response
    from aurora import ast_catalog, ast_inventory, ast_seqexport, ast_seqwrite
    base = ast_inventory.folder(cfg)
    try:
        f = ast_seqwrite.written(base, name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    if format == "nina":
        return FileResponse(f, media_type="application/json", filename=f.name)
    try:
        seq = _json.loads(f.read_text(encoding="utf-8-sig"))
        t = (ast_seqexport.read(seq, f.stem)["target"])["name"]
        o = ast_catalog.find(ast_catalog.load(base)["objects"], t) or {}
        common = ((ast_catalog.named(o) + o.get("common", [])) if o else [""])[0]
        data, fname, media = ast_seqexport.export(seq, f.stem, format, folder.strip()[:200], common)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    from urllib.parse import quote
    return Response(data, media_type=media, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"})


@router.post("/v1/aurora/astro/sky/sequence/send", dependencies=[Depends(auth)])
async def astro_sky_sequence_send(request: Request) -> dict:
    """{file}: the written sequence loaded into N.I.N.A. (its Advanced API), not started."""
    from aurora import ast_seqwrite
    name = str((await request.json()).get("file") or "")
    try:
        r = ast_seqwrite.send(cfg, name)
    except ValueError as e:
        return {"error": str(e)}
    if "sent" in r:
        log.info("audit: %s sent a sequence to N.I.N.A.: %s", me(), r["sent"])
    return r


@router.get("/v1/aurora/astro/live", dependencies=[Depends(auth)])
def astro_live() -> dict:
    """The guiding now (ROADMAP N28): PHD2's events on the telescope's PC, read only — the watcher starts on the first
    ask and stops by itself when nobody asks (ast_phd2.IDLE_S)."""
    from aurora import ast_phd2
    name, port = _host()
    if not name:
        return {"connected": False, "error": "no address: run the inventory script, or set AURORA_ASTRO_PC", "steps": []}
    return ast_phd2.watch(name, port)


@router.get("/v1/aurora/astro/nina", dependencies=[Depends(auth)])
def astro_nina() -> dict:
    """Where the mount points and what the imaging program does, live: N.I.N.A.'s Advanced API on the telescope's PC,
    read only, the site dropped (ast_nina)."""
    from aurora import ast_nina
    name, _ = _host()
    if not name:
        return {"reachable": False, "error": "no address: run the inventory script, or set AURORA_ASTRO_PC"}
    from aurora import ast_inventory as A
    site = ((A.profile(cfg) or {}).get("rig") or {}).get("site") or {}
    lat = site.get("lat")                                 # whole degrees: the polar axis's tilt in the drawing
    return {**ast_nina.status(name), "lat": round(lat) if isinstance(lat, (int, float)) else None}


@router.get("/v1/aurora/astro/nina/mount", dependencies=[Depends(auth)])
def astro_nina_mount() -> dict:
    """Only where the mount points, for the drawing that follows it every second (ast_nina.where)."""
    from aurora import ast_nina
    name, _ = _host()
    return ast_nina.where(name) if name else {"reachable": False, "error": "no address"}


def autoguide_again() -> dict | None:
    """The person's tuner as their setup says (started again after a restart by the routines' tick); its state."""
    from aurora import ast_advice as V, ast_autoguide as T, ast_inventory as A, sys_context
    d = A.folder(cfg)
    ag = V.setup(d).get("autoguide") or {}
    name, port = _host()
    t = T.ensure(sys_context.user() or "", name, port, d, ag.get("mode", "off"), ag.get("limits") or T.defaults())
    return t.state() if t else None


@router.get("/v1/aurora/astro/autoguide", dependencies=[Depends(auth)])
def astro_autoguide() -> dict:
    """The guiding tuned during the night: the mode, the limits, what PHD2 has now, the proposal or the change on trial,
    the latest actions (ast_autoguide)."""
    from aurora import ast_advice as V, ast_autoguide as T, ast_inventory as A
    d = A.folder(cfg)
    ag = V.setup(d).get("autoguide") or {}
    return {"mode": ag.get("mode", "off"), "limits": ag.get("limits") or T.defaults(V.report(cfg, with_live=False)["rows"]),
            "state": autoguide_again(), "history": T.history(d), "host": _host()[0]}


@router.put("/v1/aurora/astro/autoguide", dependencies=[Depends(auth)])
async def astro_autoguide_set(request: Request) -> dict:
    """The mode (off, propose, apply) and the limits [low, high] of each parameter, as the person sets them."""
    from aurora import ast_advice as V, ast_autoguide as T, ast_inventory as A
    body = await request.json()
    mode = body.get("mode", "off")
    if mode not in T.MODES:
        raise HTTPException(status_code=422, detail=f"mode: one of {T.MODES}")
    base = T.defaults(V.report(cfg, with_live=False)["rows"])
    limits = {}
    for k, (lo, hi) in base.items():
        v = (body.get("limits") or {}).get(k, [lo, hi])
        try:
            a, b = float(v[0]), float(v[1])
        except (TypeError, ValueError, IndexError):
            raise HTTPException(status_code=422, detail=f"limits of {k}: [low, high]") from None
        if not 0 < a <= b:
            raise HTTPException(status_code=422, detail=f"limits of {k}: 0 < low ≤ high")
        limits[k] = [int(a), int(b)] if k == "exposure_ms" else [round(a, 2), round(b, 2)]
    d = A.folder(cfg)
    V.save_part(d, "autoguide", {"mode": mode, "limits": limits})
    log.info("audit: %s set the guiding tuner to %s within %s", me(), mode, limits)
    return astro_autoguide()


# ⭕ Collimation (owner, 19 Oct: «una tab specifica nella sezione astro dedicata alla collimazione così almeno ho una parte
# dedicata e aurora la può sfruttare durante le sessioni»): the collimator's picture read, the defocused star with the
# screws learned, a night's stars across the field; the last of each kept in collimation.json for the chat.
PHOTO_BYTES = 25 * 1024 * 1024


def _collim_file() -> Path:
    from aurora import ast_inventory as A
    return A.folder(cfg) / "collimation.json"


def _collim_keep(part: str, value: dict) -> None:
    import json
    import time
    f = _collim_file()
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    d[part] = {**value, "at": time.time()}
    f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


@router.get("/v1/aurora/astro/collimation", dependencies=[Depends(auth)])
def astro_collimation() -> dict:
    """The last picture read, the last star test, the screws learned."""
    import json
    from aurora import ast_advice as V, ast_inventory as A
    try:
        d = json.loads(_collim_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    from aurora import ast_ocal
    screws = (V.setup(A.folder(cfg)).get("collimation") or {}).get("screws") or {}
    return {**d, "screws": screws, "scope": ast_ocal.scope_of(cfg)}


@router.put("/v1/aurora/astro/collimation/scope", dependencies=[Depends(auth)])
async def astro_collimation_scope(request: Request) -> dict:
    """{secondary_mm, aperture_mm, focal_mm}: the person's Newtonian, for the offset's circles (any tube, not one)."""
    from aurora import ast_advice as V, ast_inventory as A
    body = await request.json()
    try:
        s = {k: float(body[k]) for k in ("secondary_mm", "aperture_mm", "focal_mm")}
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=422, detail="secondary_mm, aperture_mm, focal_mm: numbers") from None
    if not 0 < s["secondary_mm"] < s["aperture_mm"] < s["focal_mm"] <= 20000:
        raise HTTPException(status_code=422, detail="0 < secondary < aperture < focal length")
    V.save_part(A.folder(cfg), "scope", s)
    return s


@router.post("/v1/aurora/astro/collimation/photo", dependencies=[Depends(auth)])
async def astro_collimation_photo(request: Request) -> dict:
    """The body is a picture of the collimator (a screenshot or a phone's photo of the screen): what Aurora reads in it."""
    from aurora import ast_ocal
    raw = await request.body()
    if not raw or len(raw) > PHOTO_BYTES:
        raise HTTPException(status_code=422, detail="a picture from 1 byte to 25 MB")
    out = ast_ocal.analyse(raw, ast_ocal.scope_of(cfg))
    if "error" not in out:
        _collim_keep("photo", {k: v for k, v in out.items() if k != "image"})
    log.info("audit: %s had a collimator's picture read (%d bytes)", me(), len(raw))
    return out


@router.post("/v1/aurora/astro/collimation/star", dependencies=[Depends(auth)])
async def astro_collimation_star(request: Request) -> dict:
    """{exposure_s, learned_screw?, turned?}: N.I.N.A. takes the defocused star, Aurora says what to turn (ast_donut)."""
    from aurora import ast_donut
    body = await request.json()
    learn = None
    if str(body.get("learned_screw") or "").strip():
        eighths = ast_donut.parse_turn(str(body.get("turned") or ""))
        if eighths is None:
            raise HTTPException(status_code=422, detail="turned: for example «1/8 orario» or «1/4 antiorario»")
        learn = (str(body["learned_screw"]).strip()[:40], eighths)
    out = ast_donut.run(cfg, float(body.get("exposure_s") or 3), learn)
    if "offset" in out:
        _collim_keep("star", out)
    return out


@router.get("/v1/aurora/astro/collimation/stars", dependencies=[Depends(auth)])
def astro_collimation_stars(date: str = "") -> dict:
    """A night's lights across the field (ast_stars.night): each frame's sectors and verdict, and the night's."""
    from aurora import ast_stars
    out = ast_stars.night(cfg, date.strip()[:10])
    if "error" not in out:
        out["text"] = ast_stars.night_text(out)
        _collim_keep("stars", {"date": out["date"], "codes": out["codes"], "constant": out.get("constant"),
                               "text": out["text"]})
    return out
