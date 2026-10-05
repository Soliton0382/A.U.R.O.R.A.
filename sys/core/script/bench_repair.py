# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Self-repair benchmark: is Aurora able to find and fix a real bug in her own code, end to end?

For each case a sandbox is made here (a copy of sys/core, as the self plugin makes them) and ONE realistic bug is
put in it; the live code is never touched. The agent gets only the symptom, as the owner would tell it, and the
sandbox's name. A case passes when, at the end: the sandbox's test suite is green again, and the agent proposed the
change (an approval of kind code_change for that sandbox). Every proposal is then refused here: nothing is applied.
Results: <STATUS>/bench/repair.json.

    python sys/core/script/bench_repair.py          # all cases
    python sys/core/script/bench_repair.py 1 3      # some of them
"""
from __future__ import annotations

import json
import shutil
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx  # noqa: E402

from aurora import sys_config, sys_tests  # noqa: E402

cfg = sys_config.get()
CASES = [
    {"file": "sys/core/aurora/sys_soak.py", "old": "        if all(w in line for w in needles):",
     "new": "        if any(w in line for w in needles):",
     "symptom": "Nella pagina Stato, la tabella del soak conta tra le «routine fallite» anche righe di routine che sono "
                "andate bene, e altre righe che non c'entrano."},
    {"file": "sys/core/aurora/sys_push.py",
     "old": 'any(r["kind"] == "ack" and r["id"] == push_id and r.get("dev") == dev for r in rows)',
     "new": 'any(r["kind"] == "ack" and r["id"] == push_id and r.get("dev") != dev for r in rows)',
     "symptom": "In Notifiche la riga «push confermate dai dispositivi» a volte supera il 100%: sembra che lo stesso "
                "telefono venga contato più volte per la stessa notifica."},
    {"file": "sys/core/aurora/sec_defence.py", "old": '    if incident.get("internal") or not ip.is_global:',
     "new": '    if incident.get("internal") and not ip.is_global:',
     "symptom": "Con la difesa automatica accesa, Aurora ha bloccato da sola sul firewall un indirizzo della rete di "
                "casa durante un incidente: non dovrebbe mai farlo."},
    {"file": "sys/core/aurora/kno_arxiv.py",
     "old": '        if "/html/" not in str(getattr(r, "url", "/html/")):   # ar5iv without the paper redirects to the abstract\n            continue\n',
     "new": "",
     "symptom": "Alcuni articoli arXiv vecchi, importati di recente, nel sapere contengono solo l'abstract e i menu della "
                "pagina invece del testo completo."},
]
GOAL = ("Autoriparazione, prova controllata. Il proprietario segnala: «{symptom}»\n"
        "Il codice da correggere è nella sandbox già pronta «{sid}» (una copia di sys/core): leggilo lì "
        "(sandbox_read, search_code), trova la causa, correggi lì (sandbox_replace), esegui run_tests sulla sandbox "
        "finché sono verdi, poi proponi la modifica (propose_change). Non creare un'altra sandbox.")


def make_sandbox(case: dict) -> tuple[str, Path]:
    sid = f"bench-repair-{uuid.uuid4().hex[:6]}"
    box = cfg.path("AURORA_SANDBOX_DIR") / sid
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    shutil.copytree(cfg.root / "sys" / "core", box / "sys" / "core", ignore=ignore)
    shutil.copytree(cfg.root / "sys" / "plugins", box / "sys" / "plugins", ignore=ignore)   # as the self plugin (C143)
    shutil.copy2(cfg.root / "pyproject.toml", box / "pyproject.toml")
    (box / "SANDBOX.txt").write_text(f"bench_repair {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    f = box / case["file"]
    text = f.read_text(encoding="utf-8")
    assert text.count(case["old"]) == 1, f"the bug's anchor is not unique in {case['file']}"
    f.write_text(text.replace(case["old"], case["new"]), encoding="utf-8")
    shutil.copytree(box / "sys" / "core", box / ".base" / "sys" / "core")   # its start: the bug is "the code" here
    return sid, box


def main(which: list[int]) -> int:
    key = Path("~/.config/aurora/api_key.txt").expanduser().read_text().strip()
    api = httpx.Client(base_url=f"http://{cfg['AURORA_API_HOST']}:{cfg['AURORA_API_PORT']}",
                       headers={"Authorization": f"Bearer {key}"}, timeout=60)
    rows = []
    for n, case in enumerate(CASES, 1):
        if which and n not in which:
            continue
        sid, box = make_sandbox(case)
        broken = sys_tests.run_suite(box)
        t0 = time.time()
        run = api.post("/v1/aurora/agent", json={"goal": GOAL.format(symptom=case["symptom"], sid=sid),
                                                  "remember": False}).json()["run_id"]
        while True:
            r = next((x for x in api.get("/v1/aurora/runs").json() if x["id"] == run), None)
            if r and r["done"]:
                break
            time.sleep(10)
        secs = round(time.time() - t0)
        after = sys_tests.run_suite(box)
        proposals = [a for a in api.get("/v1/aurora/approvals").json()
                     if a.get("kind") == "code_change" and (a.get("action") or {}).get("sandbox_id") == sid]
        for a in proposals:                               # a benchmark never changes the live code
            if a["status"] == "pending":
                api.post(f"/v1/aurora/approvals/{a['id']}/reject")
        fixed = after["ok"] and not broken["ok"]
        rows.append({"n": n, "file": case["file"], "sandbox": sid, "run": run, "seconds": secs,
                     "broken_tests_failed": broken["failed"], "after_ok": after["ok"], "after_failed": after["failed"],
                     "proposed": bool(proposals), "fixed": fixed, "right": fixed and bool(proposals)})
        print(f"{n}. {case['file']}: tests {broken['failed']} failing before → {after['failed']} after; "
              f"proposed {bool(proposals)}; {secs} s → {'RIGHT' if rows[-1]['right'] else 'no'}", flush=True)
    out = cfg.path("AURORA_STATUS_DIR") / "bench" / "repair.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"at": time.time(), "rows": rows}, indent=1), encoding="utf-8")
    print(f"RIGHT {sum(r['right'] for r in rows)}/{len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main([int(a) for a in sys.argv[1:] if a.isdigit()]))
