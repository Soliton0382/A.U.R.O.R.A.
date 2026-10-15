# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔭 The equipment of an astrophotography PC, read from the inventory its script writes (sys/plugins/astro/
astro_inventory.ps1, ROADMAP 79 step 0; owner, 16 Oct: «una parte nel menù chiamata astro… lo script da usare, il
comando, dove si trova il file txt che Aurora deve digerire»). Read by rules, no model: what the file says, sorted into
a profile — the PC, the software and its versions, the mount and the telescope, the cameras with their image scale,
the focuser and the filters, the guiding (PHD2's profiles), the plate solving, the site (already rounded by the
script), the darks — and what is worth a look (things missing, errors that repeat). Both versions of the script.

The files live in the person's folder (AURORA_ASTRO_DIR, usr/<name>/astro): the inventories (*.txt with «# astro
inventory»), the manuals and notes the person adds; profile() reads the latest inventory."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from . import sys_config

ARCSEC = 206.265                                       # arcsec per pixel = 206.265 × pixel size (µm) / focal length (mm)
# PHD2's guide algorithms by their number in its settings
ALGO = {"0": "nessuno", "1": "Hysteresis", "2": "Lowpass", "3": "Lowpass2", "4": "Resist Switch",
        "5": "Predictive PEC (GP)", "6": "Z-Filter"}
SIMULATED = re.compile(r"(?i)simulator|omnisim|\bsim\b|justahub|devicehub")
HEADER = "# astro inventory"


def folder(cfg: sys_config.Config) -> Path:
    d = cfg.path("AURORA_ASTRO_DIR")
    d.mkdir(parents=True, exist_ok=True)
    return d


def inventories(cfg: sys_config.Config) -> list[Path]:
    """The inventory files in the folder, the newest last (by the date the script wrote in them, else the file's)."""
    out = []
    for f in folder(cfg).glob("*.txt"):
        head = f.read_text(encoding="utf-8-sig", errors="replace")[:80]
        if head.startswith(HEADER):
            out.append(f)
    return sorted(out, key=lambda f: (f.read_text(encoding="utf-8-sig", errors="replace")[:60], f.stat().st_mtime))


def _sections(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    name = "head"
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.startswith("== "):
            name = line[3:].split(":")[0].split("(")[0].strip().lower()
            out[name] = []
        elif line.strip() and not line.startswith("# end"):
            out.setdefault(name, []).append(line.rstrip())
    return out


def _kv(s: str) -> dict[str, str]:
    """«a=1; b=x» → {a: 1, b: x}."""
    out = {}
    for part in s.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _num(s) -> float | None:
    try:
        return float(str(s).replace(",", ".").split()[0])
    except (ValueError, IndexError):
        return None


def _section(secs: dict, start: str) -> list[str]:
    return next((v for k, v in secs.items() if k.startswith(start)), [])


def parse(text: str) -> dict:
    """The inventory as a profile (see the module's words). Never raises on a strange line: it is left out."""
    secs = _sections(text)
    head = (secs.get("head") or [""])[0]
    m = re.search(r"\(script (\d+)\)", head)
    p: dict = {"written": re.sub(r"\s*\(script \d+\)", "", head.replace(HEADER, "")).strip(), "script": int(m.group(1)) if m else 1}
    p["system"] = " ".join(_section(secs, "system")[:1])
    p["disks"] = [x for x in _section(secs, "system") if x.startswith("disk ")]
    soft = {}
    for line in _section(secs, "astronomy software"):
        parts = [x.strip() for x in line.split("|")]
        if parts[0] and parts[0] not in soft:
            soft[parts[0]] = parts[1] if len(parts) > 1 else ""
    p["software"] = [{"name": k, "version": v} for k, v in soft.items()]
    drivers: dict[str, list[str]] = {}
    for line in _section(secs, "ascom"):
        if line.startswith("platform:"):
            p["ascom"] = line.split(":", 1)[1].strip()
        elif " : " in line:
            kind, rest = line.split(" : ", 1)
            label = rest.split("|")[-1].strip()
            if not SIMULATED.search(rest):
                drivers.setdefault(kind.strip(), []).append(label)
    p["drivers"] = drivers
    p["devices"] = [line.split("|")[0].strip() for line in _section(secs, "devices") if "|" in line]
    # N.I.N.A.: its profiles (the newest first in script 2), each section a key=value line
    nina, cur = [], None
    for line in _section(secs, "n.i.n.a. profiles"):
        if line.startswith("-- "):
            m = re.match(r"-- (\S+)(?: name=(.*?))? \((.*)\)$", line)
            cur = {"file": m.group(1) if m else line[3:], "name": (m.group(2) or "") if m else "", "when": m.group(3) if m else ""}
            nina.append(cur)
        elif cur is not None and line.startswith("  site:"):
            m = re.search(r"lat (-?[\d.]+) lon (-?[\d.]+) elevation (-?[\d.]+)", line)
            if m:
                cur["site"] = {"lat": float(m.group(1)), "lon": float(m.group(2)), "elevation_m": float(m.group(3))}
        elif cur is not None and line.startswith("  filters:"):
            cur["filters"] = [f.strip() for f in line.split(":", 1)[1].split(",") if f.strip()]
        elif cur is not None and " : " in line and line.startswith("  "):
            name, rest = line.strip().split(" : ", 1)
            cur[name] = _kv(rest)
        elif line.startswith("N.I.N.A. plugins:"):
            p["nina_plugins"] = [x.strip() for x in line.split(":", 1)[1].split(",") if x.strip() and not re.fullmatch(r"[\d.]+", x.strip())]
        elif line.startswith("N.I.N.A. sequences:"):
            p["sequences"] = [x.strip().removesuffix(".json") for x in line.split(":", 1)[1].split(",") if x.strip()]
    p["nina"] = nina
    errors = [line.strip() for line in _section(secs, "n.i.n.a. profiles") if "|ERROR|" in line or "|WARNING|" in line]
    said = Counter(re.sub(r"^\S+\|", "", e).split("|", 3)[-1][:160] for e in errors)
    p["nina_errors"] = [{"text": t, "times": n} for t, n in said.most_common(8)]
    p["phd2"] = _phd2(_section(secs, "phd2"))
    astap = _section(secs, "astap")
    p["astap"] = {"program": next((x.split(":", 1)[1].strip() for x in astap if x.startswith("program:")), ""),
                  "databases": next((x.split(":", 1)[1].split() for x in astap if x.startswith("star databases:")), [])}
    darks = []
    for line in _section(secs, "darks"):
        m = re.match(r"(.+): (\d+) files, e\.g\. (.+)$", line)
        if m:
            darks.append({"folder": m.group(1), "files": int(m.group(2)), "example": m.group(3)})
        elif line.startswith("looked in:"):
            p["darks_looked_in"] = [x.strip() for x in line.split(":", 1)[1].split(",") if x.strip()]
    p["darks"] = darks
    p["links"] = _links(_section(secs, "connections"))
    p["rig"] = _rig(p)
    p["checks"] = _checks(p)
    return p


def _phd2(lines: list[str]) -> dict:
    """PHD2's profiles: script 2 names the current one; script 1 listed every profile's settings one after the other,
    each starting at its «name=»."""
    out: dict = {"profiles": [], "current": "", "logs": 0, "latest_log": "", "log_lines": []}
    profiles: list[dict] = []
    for line in lines:
        s = line.strip()
        m = re.match(r"profile (\d+): (.*?)( \(current\))?$", s)
        if m:
            out["profiles"].append(m.group(2))
            if m.group(3):
                out["current"] = m.group(2)
            continue
        if s.startswith("guide logs:"):
            m = re.match(r"guide logs: (\d+); the latest: (.*)", s)
            if m:
                out["logs"], out["latest_log"] = int(m.group(1)), m.group(2).split(",")[-1].strip()
            continue
        if s.startswith("last guide log:"):                          # script 1
            out["latest_log"], out["logs"] = s.split(":", 1)[1].strip(), 1
            continue
        if s.startswith(("guide logs in:", "settings of", "profile:")):
            continue
        if line.startswith("  ") and "=" in s:
            k, v = s.split("=", 1)
            if k == "name":
                profiles.append({"name": v})
                continue
            if not profiles:
                profiles.append({"name": ""})
            profiles[-1].setdefault(k, v)
        elif line.startswith("  "):
            out["log_lines"].append(s)
    if not out["profiles"]:
        out["profiles"] = [x["name"] for x in profiles if x["name"]]
    keep = ("focalLength", "focal_length", "pixelsize", "ExposureDurationMs", "aggression", "minMove", "XGuideAlgorithm",
            "YGuideAlgorithm", "CalibrationDuration", "DitherMode", "DitherRaOnly", "LastMenuchoice", "CalDeclination")
    out["settings"] = [{"name": x["name"], **{k: x[k] for k in keep if k in x}} for x in profiles if x.get("name")]
    if not out["current"] and out["settings"]:
        out["current"] = out["settings"][0]["name"]
    return out


def _links(lines: list[str]) -> dict:
    """The programs' own servers as the PC saw them (script 3): addresses, network profile, what runs, what listens and
    to whom, the firewall's rules, each server tried from the PC itself."""
    out: dict = {"addresses": [], "profiles": [], "running": [], "listening": [], "firewall": [], "servers": [], "nina_api": ""}
    for line in lines:
        kind, _, rest = line.partition(": ")
        if kind == "address":
            out["addresses"].append(rest.split(" on ")[0])
        elif kind == "network profile":
            out["profiles"].append(rest)
        elif kind == "running":
            out["running"].append(rest.split(" (pid")[0])
        elif kind == "listening":
            m = re.match(r"(tcp|udp) (\d+) (\S+) on (\S+)", rest)
            if m:
                out["listening"].append({"proto": m.group(1), "port": int(m.group(2)), "program": m.group(3), "on": m.group(4),
                                         "network": "this PC only" not in rest})
        elif kind == "firewall":
            out["firewall"].append(rest)
        elif kind == "server":
            label, said = (rest.split(" answers", 1) + [""])[:2] if " answers" in rest else (rest.split(" does not answer")[0], "")
            out["servers"].append({"name": label.strip(), "ok": " answers" in rest, "text": said.lstrip(": 0123456789").strip()[:160]})
        elif kind.startswith("N.I.N.A. Advanced API plugin"):
            out["nina_api"] = rest
    return out


def _rig(p: dict) -> dict:
    """The equipment in one place, from N.I.N.A.'s newest profile and PHD2's current one."""
    n = p["nina"][0] if p["nina"] else {}
    tel, cam = n.get("TelescopeSettings", {}), n.get("CameraSettings", {})
    foc, fw = n.get("FocuserSettings", {}), n.get("FilterWheelSettings", {})
    ps, img, flip = n.get("PlateSolveSettings", {}), n.get("ImageFileSettings", {}), n.get("MeridianFlipSettings", {})
    focal, pixel = _num(tel.get("FocalLength")), _num(cam.get("PixelSize"))
    # N.I.N.A. writes the image folder with its backslash doubled («Z:\\\\»): shown once
    rig = {"mount": tel.get("MountName") or tel.get("LastDeviceName") or "", "mount_driver": tel.get("Id", ""),
           "telescope": tel.get("Name", ""), "focal_mm": focal, "focal_ratio": _num(tel.get("FocalRatio")),
           "camera": cam.get("LastDeviceName", ""), "pixel_um": pixel, "gain": cam.get("Gain"), "offset": cam.get("Offset"),
           "cooling_c": _num(cam.get("Temperature")), "focuser": foc.get("LastDeviceName", ""),
           "filter_wheel": fw.get("LastDeviceName", ""), "filters": n.get("filters", []),
           "guider": n.get("GuiderSettings", {}).get("GuiderName", ""), "solver": ps.get("BlindSolverType", ""),
           "images": img.get("FilePath", "").replace("\\\\", "\\"), "file_type": img.get("FileType", ""), "site": n.get("site"),
           "meridian_flip": {k: flip[k] for k in ("MinutesAfterMeridian", "MaxMinutesAfterMeridian", "PauseTimeBeforeMeridian",
                                                  "UseSideOfPier") if k in flip}}
    if focal and pixel:
        rig["scale_arcsec_px"] = round(ARCSEC * pixel / focal, 2)
    g = next((x for x in p["phd2"]["settings"] if x["name"] == p["phd2"]["current"]), None) or \
        next((x for x in p["phd2"]["settings"] if x.get("pixelsize")), None)
    if g:
        gf, gp = _num(g.get("focalLength") or g.get("focal_length")), _num(g.get("pixelsize"))
        rig["guiding"] = {"profile": g["name"], "camera": g.get("LastMenuchoice", ""), "focal_mm": gf, "pixel_um": gp,
                          "exposure_ms": _num(g.get("ExposureDurationMs")),
                          "ra_algorithm": ALGO.get(str(g.get("XGuideAlgorithm")), g.get("XGuideAlgorithm")),
                          "dec_algorithm": ALGO.get(str(g.get("YGuideAlgorithm")), g.get("YGuideAlgorithm")),
                          "aggression": _num(g.get("aggression")), "min_move": _num(g.get("minMove"))}
        if gf and gp:
            rig["guiding"]["scale_arcsec_px"] = round(ARCSEC * gp / gf, 2)
            if rig.get("scale_arcsec_px"):
                rig["guiding"]["ratio"] = round(rig["guiding"]["scale_arcsec_px"] / rig["scale_arcsec_px"], 1)
    return rig


def _checks(p: dict) -> list[dict]:
    """What is worth a look, each with why (never a verdict on the owner's choices)."""
    out = []
    rig = p["rig"]
    if not p["darks"]:
        where = ", ".join(p.get("darks_looked_in") or []) or "Documenti, D:, E:"
        out.append({"what": "Nessuna cartella di dark trovata", "why": f"cercata in {where}"
                    + ("" if p["script"] == 2 else "; lo script 1 non guardava la cartella delle immagini di N.I.N.A.: "
                       "rigenera l'inventario con lo script nuovo")})
    if not p["phd2"]["logs"] or p["phd2"]["latest_log"].endswith("(0 KB)"):
        out.append({"what": "Nessun log di guida di PHD2 utile", "why": "senza log non si giudica la guida (RMS, stelle perse)"})
    for e in p["nina_errors"]:
        if e["times"] >= 3:
            out.append({"what": f"N.I.N.A. ripete un errore ({e['times']} volte)", "why": e["text"]})
    g = rig.get("guiding") or {}
    if g.get("ratio") and g["ratio"] > 5:
        out.append({"what": f"La scala di guida è {g['ratio']}× quella di ripresa",
                    "why": "oltre circa 5× la guida fatica a vedere gli errori che la camera di ripresa registra"})
    links = p.get("links") or {}
    if p["script"] >= 3:
        for s in links.get("servers", []):
            if not s["ok"] and s["name"].startswith(("PHD2", "N.I.N.A.")):
                out.append({"what": f"{s['name']}: non risponde", "why": "per seguire la guida e la sequenza dal vivo Aurora ne ha bisogno: "
                            + ("in PHD2, Strumenti → Abilita server" if s["name"].startswith("PHD2")
                               else "installa il plugin Advanced API di N.I.N.A. (Plugins → Available) e attivalo")})
        if any("Public" in x for x in links.get("profiles", [])):
            out.append({"what": "La rete del PC è «Pubblica» per Windows",
                        "why": "Windows blocca le connessioni in entrata: per Aurora va messa su «Privata»"})
        if links.get("listening") and not any(x["network"] for x in links["listening"]):
            out.append({"what": "I server ascoltano solo il PC stesso", "why": "da un'altra macchina non si raggiungono: "
                        "nelle loro impostazioni va permesso l'accesso dalla rete di casa"})
    elif p["script"] < 3:
        out.append({"what": "Collegamenti ai programmi non letti", "why": "lo script 3, lanciato con N.I.N.A. e PHD2 aperti, "
                    "dice quali server offrono e come raggiungerli"})
    if not rig.get("scale_arcsec_px"):
        out.append({"what": "Scala di ripresa non calcolata", "why": "mancano la focale o la dimensione dei pixel nel profilo di N.I.N.A."})
    return out


# ---- the darks' library on this machine (owner, 16 Oct: «i dark li trovi nel percorso del mio pc») ---------------
DARK_FILE = re.compile(r"\.(xisf|fits?|fts)$", re.I)
# what a dark's file name says, as PixInsight's WBPP and the capture programs write it
NAME_BITS = {"exposure_s": re.compile(r"(?i)EXPOSURE[-_]?(\d+(?:\.\d+)?)s|(?<![\d.])(\d+(?:\.\d+)?)s(?:ec)?(?![a-z])"),
             "gain": re.compile(r"(?i)(?:gain[-_]?(\d+)|(\d+)[-_]?g(?:ain)?(?![a-z]))"),
             "offset": re.compile(r"(?i)(?:offset[-_]?(\d+)|(\d+)[-_]?o(?:ffset)?(?![a-z]))"),
             "temp_c": re.compile(r"(?i)(-?\d+(?:\.\d+)?)\s?(?:c|°c)(?![a-z])|temp[-_]?(-?\d+)"),
             "binning": re.compile(r"(?i)BIN[-_]?(\d)")}
# the header's few words read: never the site (an integrated dark's header carries the exact coordinates)
WANTED = ("EXPTIME", "EXPOSURE", "INSTRUME", "XBINNING", "DATE-OBS", "GAIN", "OFFSET", "CCD-TEMP", "SET-TEMP", "IMAGETYP")


def _header(f: Path) -> dict:
    """A few FITS keywords of an XISF or FITS file, from its first 256 KB (the image itself never read)."""
    with f.open("rb") as fh:
        head = fh.read(262144)
    out = {}
    if head.startswith(b"XISF0100"):
        xml = head[16:].decode("utf-8", "replace")
        for k, v in re.findall(r'<FITSKeyword name="([A-Z0-9_-]+)" value="([^"]*)"', xml):
            if k in WANTED and k not in out:
                out[k] = v.strip("' ")
        m = re.search(r"numberOfImages&quot; value=&quot;(\d+)", xml)
        if m:
            out["NCOMBINE"] = m.group(1)
    else:
        for i in range(0, len(head) - 80, 80):
            card = head[i:i + 80].decode("ascii", "replace")
            k = card[:8].strip()
            if k == "END":
                break
            if k in WANTED + ("NCOMBINE",) and card[8:10] == "= ":
                out[k] = card[10:].split("/")[0].strip().strip("' ")
    return out


def darks_library(cfg: sys_config.Config) -> dict:
    """The integrated darks in AURORA_ASTRO_DARKS_DIR (a folder of this machine), each with what its name and header say;
    the ones in a folder named «old» marked as such."""
    where = str(cfg["AURORA_ASTRO_DARKS_DIR"] or "").strip()
    if not where:
        return {"folder": "", "darks": [], "error": ""}
    d = Path(where) if Path(where).is_absolute() else cfg.root / where
    snap = folder(cfg) / "darks.json"
    if not d.is_dir():
        # a plugin's cage sees only Aurora's folders: what the API read last time, kept in the astro folder
        if snap.is_file():
            try:
                return {**json.loads(snap.read_text(encoding="utf-8")), "from": "snapshot"}
            except ValueError:
                pass
        return {"folder": where, "darks": [], "error": "cartella non trovata su questa macchina"}
    out = []
    for f in sorted(d.rglob("*")):
        if not f.is_file() or not DARK_FILE.search(f.name) or len(f.relative_to(d).parts) > 3:
            continue
        h = {}
        try:
            h = _header(f)
        except OSError:
            pass
        if "dark" not in (f.name + h.get("IMAGETYP", "")).lower():
            continue
        row = {"file": str(f.relative_to(d)), "old": "old" in [p.lower() for p in f.relative_to(d).parts[:-1]]}
        for k, rx in NAME_BITS.items():
            m = rx.search(f.name)
            if m:
                row[k] = float(next(g for g in m.groups() if g is not None))
        exp = _num(h.get("EXPTIME") or h.get("EXPOSURE"))
        row["exposure_s"] = exp if exp is not None else row.get("exposure_s")
        for k, key in (("gain", "GAIN"), ("offset", "OFFSET"), ("temp_c", "CCD-TEMP"), ("binning", "XBINNING")):
            if _num(h.get(key)) is not None:
                row[k] = _num(h.get(key))
        row["camera"] = h.get("INSTRUME", "")
        row["date"] = h.get("DATE-OBS", "")[:10]
        row["frames"] = int(h["NCOMBINE"]) if str(h.get("NCOMBINE", "")).isdigit() else None
        out.append(row)
    out.sort(key=lambda r: (r["old"], r.get("exposure_s") or 0))
    lib = {"folder": where, "darks": out, "error": ""}
    try:
        snap.write_text(json.dumps(lib, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return lib


def darks_for(lib: dict, rig: dict) -> dict:
    """Which exposures have an integrated dark for the camera as N.I.N.A. sets it (gain, offset): {"match": [s…], "other"}."""
    gain, offset = _num(rig.get("gain")), _num(rig.get("offset"))
    match, other = [], []
    for r in lib.get("darks", []):
        if r["old"]:
            continue
        same = (gain is None or r.get("gain") in (None, gain)) and (offset is None or r.get("offset") in (None, offset))
        (match if same else other).append(r.get("exposure_s"))
    return {"match": sorted(x for x in match if x is not None), "other": sorted(x for x in other if x is not None),
            "gain": gain, "offset": offset}


def profile(cfg: sys_config.Config) -> dict | None:
    """The latest inventory's profile, or None when there is none yet."""
    files = inventories(cfg)
    if not files:
        return None
    p = parse(files[-1].read_text(encoding="utf-8-sig", errors="replace"))
    p["file"] = files[-1].name
    lib = darks_library(cfg)
    if lib["darks"]:                                  # the library on this machine answers what the PC's search did not
        p["library"] = {**lib, **darks_for(lib, p["rig"])}
        p["checks"] = [c for c in p["checks"] if not c["what"].startswith("Nessuna cartella di dark")]
        said = _num(cfg["AURORA_ASTRO_DARKS_TEMP"])          # the person's word when the files do not say it
        for d in lib["darks"]:
            if d.get("temp_c") is None and said is not None:
                d["temp_c"], d["temp_from"] = said, "setting"
        cooling = p["rig"].get("cooling_c")
        if cooling is not None and not any(d.get("temp_c") is not None for d in lib["darks"]):
            p["checks"].append({"what": "La temperatura dei dark integrati non è scritta",
                                "why": f"né nel nome né nell'intestazione: valgono solo se fatti a {cooling:g} °C come la camera "
                                       "adesso; scrivila nella pagina 🔭 Astro (temperatura dei dark)"})
        elif cooling is not None and any(d.get("temp_c") not in (None, cooling) for d in lib["darks"] if not d["old"]):
            p["checks"].append({"what": "Integrated dark a un'altra temperatura",
                                "why": f"la camera si raffredda a {cooling:g} °C, alcuni dark non sono a quella temperatura"})
        if not p["library"]["match"]:
            p["checks"].append({"what": "Nessun dark integrato con il gain e l'offset di N.I.N.A.",
                                "why": f"gain {p['library']['gain']}, offset {p['library']['offset']}: i dark della libreria sono per altre impostazioni"})
    elif lib["error"]:
        p["checks"].append({"what": "Libreria dei dark non letta", "why": f"{lib['folder']}: {lib['error']}"})
    return p


def text(p: dict | None) -> str:
    """The profile in words, for the model and the plugin."""
    if not p:
        return "Nessun inventario dell'attrezzatura astro: caricalo nella pagina 🔭 Astro."
    r = p["rig"]
    lines = [f"Inventario del {p['written']} (script {p['script']}). PC: {p['system']}"]
    if r.get("telescope") or r.get("mount"):
        lines.append(f"- Telescopio: {r['telescope']} {r.get('focal_mm') or '?'} mm f/{r.get('focal_ratio') or '?'}; montatura: {r['mount']} ({r['mount_driver']})")
    if r.get("camera"):
        lines.append(f"- Camera di ripresa: {r['camera']}, pixel {r.get('pixel_um')} µm, gain {r.get('gain')}, offset {r.get('offset')}, "
                     f"raffreddata a {r.get('cooling_c')} °C; scala {r.get('scale_arcsec_px', '?')}\"/px")
    g = r.get("guiding")
    if g:
        lines.append(f"- Guida (PHD2, profilo «{g['profile']}»): {g.get('camera')}, focale {g.get('focal_mm')} mm, scala "
                     f"{g.get('scale_arcsec_px', '?')}\"/px ({g.get('ratio', '?')}× la ripresa); esposizione {g.get('exposure_ms')} ms; "
                     f"RA {g.get('ra_algorithm')}, DEC {g.get('dec_algorithm')}")
    lines.append(f"- Focheggiatore: {r.get('focuser') or '—'}; ruota portafiltri: {r.get('filter_wheel') or '—'}"
                 + (f" ({', '.join(r['filters'])})" if r.get("filters") else ""))
    lines.append(f"- Plate solving: {r.get('solver') or '—'}, cataloghi ASTAP {' '.join(p['astap']['databases']) or '—'}; "
                 f"immagini in {r.get('images') or '—'} ({r.get('file_type') or '?'})")
    if r.get("site"):
        lines.append(f"- Sito (arrotondato): lat {r['site']['lat']}, lon {r['site']['lon']}, {r['site']['elevation_m']:.0f} m")
    lines.append("- Software: " + ", ".join(f"{s['name']} {s['version']}".strip() for s in p["software"]))
    if p["darks"]:
        lines.append("- Dark sul PC astro: " + "; ".join(f"{d['folder']} ({d['files']})" for d in p["darks"][:8]))
    lib = p.get("library")
    if lib:
        lines.append(f"- Dark integrati su questa macchina ({len(lib['darks'])}): per gain {lib['gain']} e offset {lib['offset']} "
                     f"le esposizioni {', '.join(f'{x:g} s' for x in lib['match']) or 'nessuna'}"
                     + (f"; per altre impostazioni {', '.join(f'{x:g} s' for x in lib['other'])}" if lib["other"] else ""))
    lines += [f"⚠️ {c['what']}: {c['why']}" for c in p["checks"]]
    return "\n".join(lines)
