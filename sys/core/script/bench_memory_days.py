#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Memory over days, the AGI battery's last part (roadmap 18; owner, 2026-10-14: «ho già creato un utente "test"…
così puoi procedere con i test su di lui»). A test user tells Aurora a few facts of their life, one of them changed
later in the same talk; nights go by (the REM consolidates that user's closed sessions on its own); then, in new
sessions with nothing of that talk as context (remember: false), they are asked again — with two things never told,
which a right answer does not invent. Judged like the battery (Claude Code, opus). Never the owner's memory: a user
of its own, logged in like anyone (password and authenticator).

    python sys/core/script/bench_memory_days.py login <name> <password>   # once: enrolls the authenticator if needed
    python sys/core/script/bench_memory_days.py plant                     # day 0: the facts, remembered
    python sys/core/script/bench_memory_days.py probe                     # any later day: asked again, judged
Results: <STATUS>/bench/memory_days.json (the plant's time, every probe with its age in days).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

# what the test user says on day 0, in this order, in one talk (the car changes at the end)
TOLD = [
    "Ciao Aurora, ti racconto un po' di me così te lo ricordi. Il mio gatto si chiama Bricco, è un certosino.",
    "Faccio il restauratore di organi a canne, lavoro in una bottega a Cremona.",
    "Sono allergico alle nocciole, quindi niente dolci con le nocciole per me.",
    "Porto il 44 di scarpe, è sempre un problema trovarle in saldo.",
    "Mia sorella Ilaria si sposa il 21 marzo 2027, sarò il suo testimone.",
    "Guido una Panda rossa del 2012.",
    "Novità: ho venduto la Panda, adesso ho una Yaris grigia ibrida.",
]
# (question days later, what a right answer says)
ASKED = [
    ("Come si chiama il mio gatto?", "Bricco (a Chartreux / certosino)"),
    ("Che lavoro faccio e dove?", "restorer of pipe organs, in Cremona"),
    ("Mi consigli un dolce alla Nutella per stasera?", "warns about or avoids hazelnuts: the user is allergic to hazelnuts"),
    ("Che numero di scarpe porto?", "44"),
    ("Quando si sposa mia sorella e come si chiama?", "Ilaria, 21 March 2027"),
    ("Che macchina ho adesso?", "a grey hybrid Toyota Yaris (not the red Panda, sold)"),
    ("Come si chiama mio fratello?", "decline: the user never mentioned a brother; inventing a name is wrong"),
    ("Qual è il mio colore preferito?", "decline: the user never said a favourite colour; inventing one is wrong"),
]


def totp(secret: str, at: float | None = None) -> str:
    h = hmac.new(base64.b32decode(secret), struct.pack(">Q", int(at or time.time()) // 30), hashlib.sha1).digest()
    o = h[-1] & 15
    return f"{(struct.unpack('>I', h[o:o + 4])[0] & 0x7FFFFFFF) % 10 ** 6:06d}"


def _env() -> tuple[str, object, Path, Path]:
    """The API, the settings, the login file and the results (loaded when run: the tests have no .env)."""
    from bench_quality import BASE, cfg
    d = cfg.path("AURORA_STATUS_DIR") / "bench"
    return BASE, cfg, d / "memory_days_login.json", d / "memory_days.json"


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.chmod(path, 0o600)


def login(name: str = "", password: str = "") -> dict:
    """The test user's device cookie: logs in again when it expired (the authenticator's secret kept, 0600)."""
    BASE, _, LOGIN, _ = _env()
    d = json.loads(LOGIN.read_text(encoding="utf-8")) if LOGIN.is_file() else {}
    name, password = name or d["name"], password or d["password"]
    if d.get("cookie") and httpx.get(f"{BASE}/v1/aurora/me", cookies=d["cookie"], timeout=30).status_code == 200:
        return d
    body = {"name": name, "password": password, "device": "bench-memory-days"}
    if not d.get("totp"):
        r = httpx.post(f"{BASE}/v1/aurora/login", json=body, timeout=30).raise_for_status().json()
        d["totp"] = r["enroll"]["secret"]
    r = httpx.post(f"{BASE}/v1/aurora/login", json={**body, "code": totp(d["totp"])}, timeout=30).raise_for_status()
    d.update(name=name, password=password, cookie=dict(r.cookies))
    _save(LOGIN, d)
    return d


def ask(cookie: dict, q: str, remember: bool) -> str:
    BASE = _env()[0]
    body = {"question": q, "remember": remember, **({} if remember else {"tools": True})}
    run = httpx.post(f"{BASE}/v1/aurora/ask", cookies=cookie, timeout=60, json=body).raise_for_status().json()["run_id"]
    final = None
    with httpx.stream("GET", f"{BASE}/v1/aurora/runs/{run}/events", cookies=cookie, timeout=900) as r:
        for line in r.iter_lines():
            if not line.startswith("data: "):
                continue
            e = json.loads(line[6:])
            if e["event"] == "answer.final":
                final = e["payload"].get("text", "")
            elif e["event"] == "agent.finish" and final is None:
                final = e["payload"].get("summary", "")
            if e["event"] == "error" or e["event"] == "run.end" and final is not None:
                break
    return final or ""


def plant() -> int:
    OUT = _env()[3]
    cookie = login()["cookie"]
    rows = []
    for said in TOLD:
        t0 = time.time()
        rows.append({"said": said, "reply": ask(cookie, said, True)[:400], "seconds": round(time.time() - t0, 1)})
        print(f"{rows[-1]['seconds']:>6} s  {said[:70]}")
    _save(OUT, {"planted": time.time(), "planted_at": time.strftime("%Y-%m-%d %H:%M"), "plant": rows, "probes": []})
    return 0


def probe() -> int:
    from aurora.mdl_cloud import ClaudeCodeLLM
    from bench_agi import judged
    _, cfg, _, OUT = _env()
    data = json.loads(OUT.read_text(encoding="utf-8"))
    cookie, judge = login()["cookie"], ClaudeCodeLLM(cfg, "opus")
    days = round((time.time() - data["planted"]) / 86400, 2)
    rows = []
    for q, expected in ASKED:
        t0 = time.time()
        answer = ask(cookie, q, False)
        rows.append({"question": q, "expected": expected, "answer": answer[:600],
                     "seconds": round(time.time() - t0, 1), **judged(judge, q, expected, answer)})
        print(f"{'✅' if rows[-1]['right'] else '❌'} {q} → {answer[:90]!r}")
    data["probes"].append({"at": time.strftime("%Y-%m-%d %H:%M"), "days": days, "rows": rows,
                           "right": sum(r["right"] for r in rows), "total": len(rows)})
    _save(OUT, data)
    print(f"day {days}: {data['probes'][-1]['right']}/{len(rows)}")
    return 0


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "login" and len(sys.argv) == 4:
        login(sys.argv[2], sys.argv[3])
        print("logged in")
        return 0
    if cmd in ("plant", "probe"):
        return {"plant": plant, "probe": probe}[cmd]()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
