# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Benchmark of the capability forge: real needs on Aurora's own data, each with its answer computed by code.

For every need the forge builds a plugin in its stage folder (nothing is installed); the plugin's first test is run and
its numbers are compared with the truth computed at the same moment (2% tolerance on logs that grow while measured).
A need passes when every expected number is in the output. Results go to <STATUS>/bench/forge.json.

    python sys/core/script/bench_forge.py            # all needs
    python sys/core/script/bench_forge.py 1 4        # some of them
    python sys/core/script/bench_forge.py --cloud    # the cloud reasoner writes and judges (masked samples)
    python sys/core/script/bench_forge.py --roles    # as Aurora does now: writer and judge from the Models page
"""
from __future__ import annotations

import collections
import datetime as dt
import gzip
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aurora import agt_forge, sys_config  # noqa: E402
from aurora.mdl_llm import LLM  # noqa: E402
from aurora.plg_host import PluginHost  # noqa: E402

cfg = sys_config.get()
NOW = dt.datetime.now().astimezone()


def _lines(path: Path):
    """The live log and its rotated copies (<name>.<time>.log.gz): a window of hours often spans several (C94)."""
    stem = path.name.removesuffix(".log")
    for f in sorted(path.parent.glob(f"{stem}.*.log.gz")) + [path]:
        if not f.is_file():
            continue
        opener = gzip.open if f.suffix == ".gz" else open
        with opener(f, "rt", errors="replace") as h:
            yield from h


def _when(line: str):
    try:
        return dt.datetime.fromisoformat(line[:29])
    except ValueError:
        return None


def harvest_by_source(hours=24):
    c = collections.Counter()
    for line in _lines(cfg.path("AURORA_LOG_DIR") / "harvester" / "harvester.log"):
        m = re.match(r"(\S+) INFO aurora\.harvester (.+?) -> (\w+): ", line)   # keys may hold spaces (Wikipedia titles)
        if m and (t := _when(line)) and t >= NOW - dt.timedelta(hours=hours):
            k = m[2]
            c["arxiv" if re.match(r"\d{4}\.\d{4,5}", k) else "europepmc" if k.startswith("PMC") else k.split(":")[0]] += 1
    return dict(c)


def firewall_denied(hours=6):
    seen = set()                                         # a line repeated in two files is one connection
    for line in _lines(cfg.path("AURORA_LOG_DIR") / "firewall" / "firewall.log"):
        if re.search(r'(status|log_subtype)="Denied"', line) and (t := _when(line)) and t >= NOW - dt.timedelta(hours=hours):
            seen.add(line)
    return {"denied": len(seen)}


def incidents_by_severity(days=7):
    items = json.loads((cfg.path("AURORA_STATUS_DIR") / "incidents.json").read_text())
    since = NOW - dt.timedelta(days=days)
    c = collections.Counter(i["severity"] for i in items
                            if dt.datetime.strptime(i["received"], "%Y-%m-%dT%H:%M:%S%z") >= since)
    return dict(c)


def warnings_by_component(hours=24):
    c = collections.Counter()
    for f in cfg.path("AURORA_LOG_DIR").glob("https/caddy*.log"):       # Caddy writes JSON lines: level and epoch
        for line in open(f, errors="replace"):
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("level") in ("warn", "error") and dt.datetime.fromtimestamp(e.get("ts", 0)).astimezone() >= NOW - dt.timedelta(hours=hours):
                c["https"] += 1
    for f in cfg.path("AURORA_LOG_DIR").glob("*/*.log"):
        for line in _lines(f):
            m = re.match(r"(\S+) (WARNING|ERROR|CRITICAL) ", line)
            if m and (t := _when(line)) and t >= NOW - dt.timedelta(hours=hours):
                c[f.parent.name] += 1
    return dict(c.most_common(5))


def dreams(days=7):
    d = cfg.path("AURORA_IMAGE_DIR")
    since = time.time() - days * 86400
    return {"dreams": sum(1 for f in d.glob("dream-*.png") if f.stat().st_mtime >= since)}


def documents_pdf():
    files = list(cfg.path("AURORA_DOCUMENTS_DIR").glob("*.pdf"))
    return {"pdf": len(files)}


def routines_active():
    from aurora import sys_users_layout
    rs = json.loads((sys_users_layout.place(cfg, "state", None) / "routines.json").read_text())
    return {"active": sum(1 for r in rs if r.get("enabled", True)), "total": len(rs)}


def log_mb(component="harvester"):
    size = sum(f.stat().st_size for f in (cfg.path("AURORA_LOG_DIR") / component).glob("*"))
    return {"mb": round(size / 1048576, 1)}


NEEDS = [
    ("Quanti documenti ha raccolto l'harvester nelle ultime 24 ore, per fonte (arxiv, normattiva, europepmc, github, medrxiv, biorxiv, wikipedia), dal log dell'harvester", harvest_by_source),
    ("Quante connessioni ha negato il firewall nelle ultime 6 ore (righe Denied nel log del firewall)", firewall_denied),
    ("Quanti incidenti di sicurezza negli ultimi 7 giorni, per gravità (high, medium, low), da status/incidents.json", incidents_by_severity),
    # the truth counts every line of level WARNING or above: the need says so (the judge read "WARNING o ERROR" literally)
    ("Quante righe WARNING, ERROR o CRITICAL ha scritto ogni componente di Aurora nelle ultime 24 ore (le 5 con più righe), dai log in sys/logs", warnings_by_component),
    ("Quanti sogni (immagini dream-*.png) ha dipinto Aurora negli ultimi 7 giorni, nella cartella delle immagini", dreams),
    ("Quanti PDF ci sono nella cartella dei documenti di Aurora", documents_pdf),
    ("Quante routine sono attive e quante in tutto, dal file routines.json dell'utente", routines_active),
    ("Quanto spazio occupano, in MB, i log dell'harvester (cartella sys/logs/harvester)", log_mb),
]


def numbers(text: str) -> list[float]:
    """Numbers as written in Italian or English: 17.853 / 17,853 / 1.234,5 / 12.5."""
    out = []
    for raw in re.findall(r"\d[\d.,]*", text):
        s = raw.rstrip(".,")
        if re.fullmatch(r"\d{1,3}([.,]\d{3})+", s):
            s = re.sub(r"[.,]", "", s)
        elif "." in s and "," in s:                      # Italian: 1.234,5
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", ".")
        try:
            out.append(float(s))
        except ValueError:
            pass
    return out


def passes(expected: dict, text: str) -> tuple[bool, list]:
    got = numbers(text)
    missing = []
    for k, v in expected.items():
        tol = (0.06 if v != int(v) else 0) if v <= 50 else max(1, abs(v) * 0.02)   # 5.64 MB is 5.6 MB rounded
        if not any(abs(g - v) <= tol for g in got):
            missing.append((k, v))
    return not missing, missing


def run_tool(stage: str, manifest: dict) -> str:
    host = PluginHost(cfg)
    from aurora.plg_host import Plugin
    t = manifest["tests"][0]
    p = Plugin(manifest["name"], Path(stage), manifest)

    async def call(session):
        return await session.call_tool(t["tool"], t.get("args") or {})
    res = host._run(host._session(p, call))
    return "\n".join(c.text for c in getattr(res, "content", []) if getattr(c, "type", "") == "text")


def main(which: list[int], cloud: bool = False, roles: bool = False) -> None:
    host, rows, judge = PluginHost(cfg), [], None
    if roles:                                            # the owner's assignments (mdl_router), masked when cloud
        from aurora import mdl_router
        local = LLM(cfg)
        llm, judge = mdl_router.model_for("forge_write", local, cfg), mdl_router.model_for("forge_judge", local, cfg)
        masker = None if mdl_router.is_local(llm, local) else agt_forge.Masker(cfg)
        print("writer:", getattr(llm, "name", "?"), getattr(llm, "model", ""), "| judge:", getattr(judge, "name", "?"),
              getattr(judge, "model", ""), flush=True)
    elif cloud:
        from aurora.mdl_cloud import ClaudeCodeLLM
        llm, masker = ClaudeCodeLLM(cfg), agt_forge.Masker(cfg)
    else:
        llm, masker = LLM(cfg), None
    for i, (need, truth) in enumerate(NEEDS, 1):
        if which and i not in which:
            continue
        t0 = time.time()
        res = agt_forge.build(cfg, llm, host, {"id": f"bench{i}", "need": need, "why": "benchmark"}, lambda e, p: None, masker,
                              judge=judge)
        row = {"n": i, "need": need, "built": res["ok"], "attempts": res.get("attempts"), "seconds": round(time.time() - t0)}
        if res["ok"]:
            # A23: the truth's window is now, the moment the plugin runs too, not the script's start (minutes before:
            # what entered or left a 24 h window meanwhile was counted on one side only)
            global NOW
            NOW = dt.datetime.now().astimezone()
            out = run_tool(res["stage"], res["manifest"])
            expected = truth()
            ok, missing = passes(expected, out)
            row.update(right=ok, expected=expected, missing=missing, output=out[:600])
        else:
            row.update(right=False, errors=res["errors"][:2])
        rows.append(row)
        print(f"{i}. built={row['built']} right={row['right']} {row['seconds']} s — {need[:70]}"
              + (f" | missing {row.get('missing')}" if row.get("built") and not row["right"] else ""), flush=True)
    right = sum(r["right"] for r in rows)
    print(f"RIGHT {right}/{len(rows)}; built {sum(r['built'] for r in rows)}/{len(rows)}")
    out = cfg.path("AURORA_STATUS_DIR") / "bench"
    out.mkdir(parents=True, exist_ok=True)
    (out / ("forge_roles.json" if roles else "forge_cloud.json" if cloud else "forge.json")).write_text(
        json.dumps({"at": NOW.isoformat(), "cloud": cloud, "roles": roles, "rows": rows}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main([int(x) for x in sys.argv[1:] if x.isdigit()], cloud="--cloud" in sys.argv, roles="--roles" in sys.argv)
