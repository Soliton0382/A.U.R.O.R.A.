# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📤 A written sequence for other acquisition software (owner, 19 Oct: «rendere compatibile questa funzionalità anche
con altri software di pianificazione»). Read from the N.I.N.A. sequence Aurora wrote (ast_seqwrite): the target, and for
each block of exposures its count, length, gain, offset, binning and filter; the dither's interval and the cooling.
Written as each program reads it, from its own source code (19 Oct):
- Ekos (KStars): a capture queue .esq (sequencejob.cpp loadFrom: Exposure in seconds, Count, Binning, Filter by name,
  Temperature only with force='true', GuideDitherPerJob N or -1, gain and offset as driver properties — both CCD_GAIN/
  CCD_OFFSET and CCD_CONTROLS written: capturedeviceadaptor.cpp takes the one the camera has) and a scheduler list .esl
  (J2000 RA in decimal hours, Dec in degrees; the .esq by absolute path on the Ekos machine), zipped together.
- CCDciel: a .targets file, version 5 (cu_targets.pas SaveTargets: Lazarus XMLConfig, each key an element with a Value
  attribute under CONFIG; RA as 20h51m00.72s, Dec as +44d24m03.60s, J2000). Gain, offset and the cooling temperature
  are not in it: CCDciel takes them from its own settings (said in the notes).
- A target list as Telescopius exports it (CSV), imported by N.I.N.A., SGP and APT: the target only, the exposures set
  in the program. Columns named «(j2000)»: a column called just «Right Ascension» makes N.I.N.A. read the declination
  from it (SimpleSequenceVM.cs).
None of these loaded in the real program yet (none on this machine)."""
from __future__ import annotations

import csv
import io
import json
import zipfile
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

from . import ast_sequence

FORMATS = ("nina", "ekos", "ccdciel", "csv")


def _values(x):
    return (x.get("$values") or []) if isinstance(x, dict) else (x or [])


def _kind(n: dict) -> str:
    return str(n.get("$type", "")).split(",")[0].rsplit(".", 1)[-1]


def jobs(seq: dict) -> list[dict]:
    """The blocks of exposures in order: {count, s, gain, offset, bin, filter}; the filter the last one switched to."""
    out, state = [], {"filter": ""}

    def walk(n, count):
        if isinstance(n, list):
            for x in n:
                walk(x, count)
            return
        if not isinstance(n, dict):
            return
        k = _kind(n)
        if k == "SwitchFilter":
            f = n.get("Filter")
            state["filter"] = (f.get("_name") or f.get("Name") or "") if isinstance(f, dict) else str(f or "")
        loops = [c for c in _values(n.get("Conditions")) if isinstance(c, dict) and _kind(c) == "LoopCondition"]
        if loops:
            count = int(loops[0].get("Iterations") or 1)
        if k == "TakeExposure" and str(n.get("ImageType", "LIGHT")).upper() == "LIGHT":
            b = n.get("Binning") or {}
            out.append({"count": int(count or n.get("ExposureCount") or 1), "s": float(n.get("ExposureTime") or 0),
                        "gain": n.get("Gain"), "offset": n.get("Offset"), "bin": (int(b.get("X") or 1), int(b.get("Y") or 1)),
                        "filter": state["filter"]})
        for key in ("Items", "Triggers"):
            walk(_values(n.get(key)), count)

    walk(seq, 0)
    return out


def read(seq: dict, name: str = "") -> dict:
    p = ast_sequence.parse(json.dumps(seq), name)
    if not p["targets"]:
        raise ValueError("la sequenza non ha un oggetto con le coordinate")
    return {**p, "target": p["targets"][0], "jobs": jobs(seq)}


def _num(x) -> str:
    return f"{float(x):g}"


def _usable(v) -> bool:
    return v is not None and float(v) >= 0              # N.I.N.A.'s -1: the camera's own value


def esq(p: dict) -> str:
    t, lines = p["target"], ["<?xml version=\"1.0\" encoding=\"UTF-8\"?>", "<SequenceQueue version='2.6'>"]
    for j in p["jobs"]:
        lines += ["<Job>", f"<Exposure>{_num(j['s'])}</Exposure>",
                  f"<Binning><X>{j['bin'][0]}</X><Y>{j['bin'][1]}</Y></Binning>"]
        if p.get("cool_c") is not None:
            lines.append(f"<Temperature force='true'>{_num(p['cool_c'])}</Temperature>")
        if j["filter"]:
            lines.append(f"<Filter>{escape(j['filter'])}</Filter>")
        lines += ["<Type>Light</Type>", f"<TargetName>{escape(t['name'])}</TargetName>", f"<Count>{j['count']}</Count>",
                  "<Delay>0</Delay>", f"<GuideDitherPerJob>{int(p['dither_every']) if p.get('dither_every') else -1}</GuideDitherPerJob>"]
        props = []
        if _usable(j["gain"]):
            props.append(f"<PropertyVector name='CCD_GAIN'><OneElement name='GAIN'>{_num(j['gain'])}</OneElement></PropertyVector>")
        if _usable(j["offset"]):
            props.append(f"<PropertyVector name='CCD_OFFSET'><OneElement name='OFFSET'>{_num(j['offset'])}</OneElement></PropertyVector>")
        both = [f"<OneElement name='{n}'>{_num(j[k])}</OneElement>" for n, k in (("Gain", "gain"), ("Offset", "offset")) if _usable(j[k])]
        if both:
            props.append(f"<PropertyVector name='CCD_CONTROLS'>{''.join(both)}</PropertyVector>")
        lines += [f"<Properties>{''.join(props)}</Properties>", "</Job>"]
    return "\n".join(lines + ["</SequenceQueue>", ""])


def esl(p: dict, esq_path: str, min_alt: float = 30) -> str:
    t = p["target"]
    steps = ["Track"] + (["Focus"] if p.get("autofocus") else []) + ["Align"] + (["Guide"] if p.get("guiding") else [])
    return "\n".join([
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>", "<SchedulerList version='2.2'>", "<Profile>Default</Profile>", "<Job>",
        "<JobType lead='true'/>", f"<Name>{escape(t['name'])}</Name>", "<Group></Group>",
        f"<Coordinates><J2000RA>{t['ra_h']:.6f}</J2000RA><J2000DE>{t['dec_deg']:.5f}</J2000DE></Coordinates>",
        "<PositionAngle>0</PositionAngle>", f"<Sequence>{escape(esq_path)}</Sequence>",
        "<StartupCondition><Condition>ASAP</Condition></StartupCondition>",
        f"<Constraints><Constraint value='{min_alt:g}'>MinimumAltitude</Constraint><Constraint>EnforceTwilight</Constraint></Constraints>",
        "<CompletionCondition><Condition>Sequence</Condition></CompletionCondition>",
        f"<Steps>{''.join(f'<Step>{s}</Step>' for s in steps)}</Steps>", "</Job>", "</SchedulerList>", ""])


def ekos(p: dict, stem: str, folder: str = "") -> bytes:
    """The .esq and the .esl zipped; the .esl names the .esq in the folder given (the Ekos machine's), else bare."""
    path = f"{folder.rstrip('/')}/{stem}.esq" if folder else f"{stem}.esq"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{stem}.esq", esq(p))
        z.writestr(f"{stem}.esl", esl(p, path))
        z.writestr("LEGGIMI.txt", "Ekos: apri il file .esl nello Scheduler (o il .esq in Capture).\n"
                   f"Il .esl cerca la sequenza in: {path}\nSe l'hai salvata altrove, sceglila di nuovo nel lavoro.\n"
                   "Guadagno e offset sono scritti per entrambi i modi dei driver INDI (CCD_GAIN e CCD_CONTROLS).\n")
    return buf.getvalue()


def sexa(v: float, hours: bool, seps: tuple[str, str, str], sign: bool) -> str:
    s = "-" if v < 0 else ("+" if sign else "")
    v = abs(v)
    a = int(v)
    m = int((v - a) * 60)
    sec = round(((v - a) * 60 - m) * 60, 2)
    if sec >= 60:
        sec, m = 0.0, m + 1
    if m >= 60:
        m, a = 0, a + 1
    if hours:
        a %= 24
    return f"{s}{a:02d}{seps[0]}{m:02d}{seps[1]}{sec:05.2f}{seps[2]}"


def ccdciel(p: dict, stem: str) -> bytes:
    t = p["target"]
    root = ET.Element("CONFIG")

    def put(path: str, value):
        n = root
        for part in path.strip("/").split("/"):
            c = n.find(part)
            n = c if c is not None else ET.SubElement(n, part)
        n.set("Value", ("True" if value else "False") if isinstance(value, bool) else str(value))

    put("/Version", 5)
    put("/ListName", stem)
    put("/TargetNum", 1)
    put("/RepeatCount", 1)
    put("/Startup/CoolCamera", p.get("cool_c") is not None)
    base = "/Targets/Target1"
    put(f"{base}/ObjectName", t["name"])
    put(f"{base}/Plan", stem)
    put(f"{base}/RA", sexa(t["ra_h"], True, ("h", "m", "s"), False))
    put(f"{base}/Dec", sexa(t["dec_deg"], False, ("d", "m", "s"), True))
    put(f"{base}/PA", "-")
    put(f"{base}/Magnitude", "-")
    put(f"{base}/RepeatCount", 1)
    put(f"{base}/Plan/Name", stem)
    put(f"{base}/Plan/StepNum", len(p["jobs"]))
    for i, j in enumerate(p["jobs"], 1):
        s = f"{base}/Plan/Steps/Step{i}"
        put(f"{s}/Type", 0)
        put(f"{s}/Description", f"{j['count']}x{_num(j['s'])}s {j['filter']}".strip())
        put(f"{s}/FrameType", "Light")
        put(f"{s}/Exposure", _num(j["s"]))
        put(f"{s}/Binning", f"{j['bin'][0]}x{j['bin'][1]}")
        put(f"{s}/Filter", j["filter"])
        put(f"{s}/Count", j["count"])
        put(f"{s}/Dither", bool(p.get("dither_every")))
        put(f"{s}/DitherCount", int(p.get("dither_every") or 1))
        put(f"{s}/AutofocusStart", False)
        put(f"{s}/Done", 0)
    ET.indent(root, "  ")
    return b'<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding="utf-8") + b"\n"


HEAD = ["Catalogue Entry", "Familiar Name", "Alternative Entries", "Type", "Constellation", "Right Ascension (j2000)",
        "Declination (j2000)", "Magnitude", "Size", "Surface Brightness (mag/arcsec2)", "Rises over 10º", "Transit Time",
        "Sets below 10º", "Maximum Altitude", "Position Angle (East)", "Next Opposition", "Notes",
        "Right Ascension (jNow)", "Declination (jNow)", "Label"]


def target_csv(p: dict, common: str = "") -> bytes:
    t = p["target"]
    note = "; ".join(f"{j['count']}x{_num(j['s'])}s" + (f" gain {_num(j['gain'])}" if _usable(j["gain"]) else "")
                     + (f" offset {_num(j['offset'])}" if _usable(j["offset"]) else "") + (f" {j['filter']}" if j["filter"] else "")
                     for j in p["jobs"])
    row = dict.fromkeys(HEAD, "")
    row.update({"Catalogue Entry": t["name"], "Familiar Name": common or t["name"], "Notes": note, "Label": "Aurora",
                "Right Ascension (j2000)": sexa(t["ra_h"], True, ("h ", "' ", '"'), False),
                "Declination (j2000)": sexa(t["dec_deg"], False, ("º ", "' ", '"'), False)})
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=HEAD, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    w.writeheader()
    w.writerow(row)
    return buf.getvalue().encode("utf-8")


def export(seq: dict, stem: str, fmt: str, folder: str = "", common: str = "") -> tuple[bytes, str, str]:
    """(content, file name, media type) of the sequence in that format."""
    if fmt not in FORMATS[1:]:
        raise ValueError(f"formato: uno di {', '.join(FORMATS)}")
    p = read(seq, stem)
    if not p["jobs"]:
        raise ValueError("la sequenza non ha pose di luce da esportare")
    if fmt == "ekos":
        return ekos(p, stem, folder), f"{stem} Ekos.zip", "application/zip"
    if fmt == "ccdciel":
        return ccdciel(p, stem), f"{stem}.targets", "application/xml"
    return target_csv(p, common), f"{stem}.csv", "text/csv"
