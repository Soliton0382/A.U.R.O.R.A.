# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Lessons on the virtual bench, saved where the person sees them (C747; the owner, 26 Nov: «insegniamo qualcosa ad
aurora… un utilizzo normale»).

Inside the bench, for each lesson: one demonstration with real keys, recorded by Aurora's recorder in a process of
its own, turned into a draft (draft.build), then the draft replayed with real keys and NEW values a few times, each
judged on the outcome (the file's text, the folder made, the number read), never on the anchors. Outside the bench
(the person's own HOME): a draft whose check passed is saved in the personal library (store.save_draft) and every
trial beside it (store.record_trial), so «Cosa ho imparato» shows it with its record.
    python3 -I -B teach.py [--lessons kate,kcalc,konsole,writer] [--trials 3]"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE.parents[1]
sys.path.insert(0, str(CORE))

from desk import library_check  # noqa: E402
from desk.app import draft  # noqa: E402
from desk.bench import bench as benchmod  # noqa: E402

TEXTS = ["Lista della spesa: pane e latte", "Appunti di oggi", "Prova numero tre", "Quarta nota"]
EXPRS = [("12+30", "42"), ("7*8", "56"), ("100-58", "42"), ("9*9", "81")]
DIRS = ["Ricette", "Foto-estate", "Bollette", "Progetti"]


def lessons(home: Path) -> dict:
    """name -> (program meta, demonstration argv, actions, how to replay: params(new value) and outcome)."""
    return {
        "kate": {"name": "scrivi-e-salva", "prog": "kate", "argv": lambda f: ["/usr/bin/kate", str(f)],
                 "file": True, "acts": lambda v: [("type", v), ("tap", "Alt", "f"), ("tap", "s")], "values": TEXTS},
        "kcalc": {"name": "calcola", "prog": "kcalc", "argv": lambda f: ["/usr/bin/kcalc"], "file": False,
                  "acts": lambda v: [("type", v[0]), ("tap", "Enter")], "values": EXPRS},
        "konsole": {"name": "crea-cartella", "prog": "konsole", "dir": True,
                    "argv": lambda d: ["/usr/bin/konsole", "--separate", "--workdir", str(d)],
                    "acts": lambda v: [("type", f"mkdir {v}"), ("tap", "Enter")], "values": DIRS},
        "writer": {"name": "scrivi-e-salva", "prog": "soffice", "file": True, "suffix": ".odt",
                   "argv": lambda f: ["/usr/bin/soffice", "--writer", "--norestore", "--nologo", str(f)],
                   "template": True,
                   "acts": lambda v: [("type", v), ("tap", "Ctrl", "s")], "values": TEXTS,
                   "app_names": ("soffice", "soffice.bin", "LibreOffice", "libreoffice"), "wait_s": 40.0},
    }


LO_PROFILE = """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema">
<item oor:path="/org.openoffice.Office.Common/Misc"><prop oor:name="ShowTipOfTheDay" oor:op="fuse"><value>false</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Misc"><prop oor:name="FirstRun" oor:op="fuse"><value>false</value></prop></item>
<item oor:path="/org.openoffice.Setup/Office"><prop oor:name="FirstStartWizardCompleted" oor:op="fuse"><value>true</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Save/Document"><prop oor:name="WarnAlienFormat" oor:op="fuse"><value>false</value></prop></item>
</oor:items>
"""


def lo_first_start_off(home: Path) -> None:
    """The bench HOME is new at every run: LibreOffice would open its welcome and tip-of-the-day windows, and the
    demonstration's keys went there (26 Nov). A profile that says they were seen."""
    f = home / ".config" / "libreoffice" / "4" / "user" / "registrymodifications.xcu"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(LO_PROFILE, encoding="utf-8")


def odt_template(b, work: Path) -> Path:
    """An empty Writer document, made once by LibreOffice itself without a screen: the lesson opens an existing file,
    so Ctrl+S saves it in place (the save dialog's name field cannot be written through accessibility, as with Kate)."""
    import subprocess
    src = work / "vuoto.txt"
    src.write_text("", encoding="utf-8")
    subprocess.run(["/usr/bin/soffice", "--headless", "--norestore", "--convert-to", "odt", "--outdir", str(work),
                    str(src)], env=b.wenv(), stdout=b.out("odt"), stderr=-2, timeout=120, check=False)
    return work / "vuoto.odt"


def inner(a) -> int:
    from desk.bench import a11y, lib_run
    from desk.bench.d1_measure import demonstrate
    b = benchmod.Bench(os.environ["N152_BENCH"])
    out = b.base / "teach_results.json"
    home = Path(b.desc["home"])
    res, kb = {"lessons": []}, {}
    try:
        b.up()
        a11y.init()
        from gi.repository import Atspi
        Atspi.set_timeout(2000, 15000)
        lo_first_start_off(home)
        for key in a.lessons.split(","):
            L = lessons(home)[key]
            r = {"lesson": key, "program": L["prog"], "name": L["name"], "trials": []}
            try:
                work = home / f"teach-{key}"
                work.mkdir(exist_ok=True)
                v0 = L["values"][0]
                target = work / ("demo" + L.get("suffix", ".txt")) if L.get("file") else work
                tpl = odt_template(b, work) if L.get("template") else None
                if tpl:
                    import shutil
                    shutil.copyfile(tpl, target)
                rec = demonstrate(b, kb, f"teach-{key}", L["argv"](target), L["acts"](v0),
                                  app_names=L.get("app_names", ()), wait_s=L.get("wait_s", 5.0))
                r["counters"] = rec.get("counters")
                prog = {"name": L["prog"], "package": L["prog"], "exe": L["argv"](target)[0], "version": "4:25.12",
                        "args": L["argv"](target)[1:]}
                d = draft.build(rec.get("events", []), prog, loc="it", network=False)
                proc = d["procedure"]
                proc["id"] = f"per:linux/{L['prog']}/{L['name']}"
                r["flags"], r["steps"] = d["flags"], [s["do"] for s in proc["steps"]]
                root = b.base / "per"
                pf = root / "linux" / L["prog"] / f"{L['name']}.json"
                pf.parent.mkdir(parents=True, exist_ok=True)
                pf.write_text(json.dumps(proc, ensure_ascii=False))
                r["check"] = library_check.check(pf, root, ns="per")
                r["procedure"] = proc
                if L.get("dir"):
                    r["demo_ok"] = (work / v0).is_dir()
                elif L.get("file") and not L.get("suffix"):
                    r["demo_ok"] = target.exists() and v0 in target.read_text(errors="replace")
                texts = [k for k in proc["params"] if proc["params"][k]["kind"] == "text"]
                paths = [k for k in proc["params"] if proc["params"][k]["kind"] == "path"]
                for i, v in enumerate(L["values"][1:1 + a.trials]):
                    rw = home / f"teach-{key}-{i}"
                    rw.mkdir(exist_ok=True)
                    params = {}
                    nf = rw / ("nuovo" + L.get("suffix", ".txt"))
                    if tpl:
                        shutil.copyfile(tpl, nf)
                        before_size = nf.stat().st_size
                    if paths:
                        params[paths[0]] = str(nf if L.get("file") else rw)
                    if texts:
                        params[texts[0]] = v[0] if key == "kcalc" else v
                    lib_run.KEYS.update(kb=kb["kb"])
                    rr = lib_run.run_one(b, proc, params, "it", rw)
                    if key == "kcalc":
                        got = next((s.get("read") for s in rr["steps"] if s["do"] == "read"), None)
                        ok = got == v[1]
                    elif L.get("dir"):
                        got = sorted(x.name for x in rw.iterdir() if x.is_dir())
                        ok = got == [v]
                    elif L.get("suffix"):                      # the text is inside the zip: read content.xml
                        import zipfile
                        try:
                            got = v in zipfile.ZipFile(nf).read("content.xml").decode("utf-8", "replace")
                        except (OSError, KeyError, zipfile.BadZipFile):
                            got = False
                        ok = got
                    else:
                        got = nf.read_text().rstrip("\n") if nf.exists() else None
                        ok = got == v
                    r["trials"].append({"ok": bool(ok and rr.get("ok")), "got": got, "error": rr.get("error"),
                                        "steps": [{"n": x["n"], "ok": x.get("ok")} for x in rr["steps"]]})
            except Exception:                                   # noqa: BLE001
                import traceback
                r["fatal"] = traceback.format_exc()[-900:]
            res["lessons"].append(r)
            out.write_text(json.dumps(res, indent=1, ensure_ascii=False))
    except Exception:                                           # noqa: BLE001
        import traceback
        res["fatal"] = traceback.format_exc()[-900:]
    finally:
        out.write_text(json.dumps(res, indent=1, ensure_ascii=False))
        if kb.get("kb"):
            kb["kb"].close()
            kb["pt"].close()
        b.down()
    return 0


def save(results: Path) -> list:
    """Outside the bench: drafts whose check passed go to the person's library, with every trial."""
    from desk.app import store
    said = []
    for r in json.loads(results.read_text()).get("lessons", []):
        if r.get("fatal") or r.get("check") or not r.get("procedure"):
            said.append(f"{r['lesson']}: non salvata ({(r.get('fatal') or str(r.get('check')))[-200:]})")
            continue
        s = store.save_draft(r["procedure"], "linux", r["program"], r["name"], {})
        if s["errors"]:
            said.append(f"{r['lesson']}: non salvata ({s['errors']})")
            continue
        p = Path(s["path"])
        for t in r["trials"]:
            store.record_trial(p, t["ok"], t["steps"])
        said.append(f"{r['lesson']}: salvata, prove {sum(t['ok'] for t in r['trials'])}/{len(r['trials'])}")
    return said


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scratch", default=str(benchmod.default_scratch()))
    ap.add_argument("--lessons", default="kate,kcalc,konsole,writer")
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--inside", action="store_true")
    ap.add_argument("--no-save", action="store_true")
    a = ap.parse_args()
    if a.inside:
        return inner(a)
    desc = benchmod.prepare(Path(a.scratch))
    rc = benchmod.reexec_inside(desc, ["/usr/bin/python3", "-I", "-B", str(Path(__file__).resolve()), "--inside",
                                       "--lessons", a.lessons, "--trials", str(a.trials)])
    results = Path(desc["base"]) / "teach_results.json"
    print(f"results: {results}")
    if not a.no_save and results.exists():
        for line in save(results):
            print(line)
    return rc


if __name__ == "__main__":
    sys.exit(main())
