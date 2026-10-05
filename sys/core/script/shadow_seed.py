# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Seeding the shadow (owner, 2026-10-05): Aurora is asked many questions on purpose, so that the shadow of verified
answers (kno_shadow) starts full instead of empty.

Each question goes through the real API with "remember": false (nobody asked it: it does not become a conversation)
and "shadow_seed": true (a verified answer with sources casts its shadow, marked as a seed). About 50 s a question:
128 questions take about 2 hours — run it in the day, not while aurora-rem dreams or studies (one GPU, one job).
Stop it any time (Ctrl-C): it starts again where it stopped (the log: <STATUS>/bench/shadow_seed.jsonl).

    python sys/core/script/shadow_seed.py                    # the questions not asked yet (config/shadow_seed_questions.json)
    python sys/core/script/shadow_seed.py --limit 20 --domains physics,history
    python sys/core/script/shadow_seed.py --file my_questions.json   # [{"domain": "...", "question": "..."}]
    python sys/core/script/shadow_seed.py --export           # config/shadow_seed.json: the seed answers with public sources only
    python sys/core/script/shadow_seed.py --import           # a published seed into this installation's shadow
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx  # noqa: E402

from aurora import sys_config  # noqa: E402

cfg = sys_config.get()
BASE = f"http://{cfg['AURORA_API_HOST']}:{cfg['AURORA_API_PORT']}"
HEAD = {"Authorization": f"Bearer {cfg['AURORA_API_KEY']}"}
CONFIG = Path(__file__).resolve().parents[1] / "config"


def ask(q: str) -> dict:
    run = httpx.post(f"{BASE}/v1/aurora/ask", headers=HEAD, timeout=60,
                     json={"question": q, "remember": False, "shadow_seed": True, "suggest": True}).json()["run_id"]
    t0, final = time.time(), None
    with httpx.stream("GET", f"{BASE}/v1/aurora/runs/{run}/events", headers=HEAD, timeout=900) as r:
        for line in r.iter_lines():
            if not line.startswith("data: "):
                continue
            e = json.loads(line[6:])
            if e["event"] == "answer.final":
                final = e["payload"]
            if e["event"] == "error" or e["event"] == "run.end" and final is not None:
                break
    final = final or {}
    return {"seconds": round(time.time() - t0, 1), "abstained": bool(final.get("abstained", True)),
            "sources": len(final.get("sources") or []), "error": not final}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--file", default=str(CONFIG / "shadow_seed_questions.json"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--domains", default="")
    ap.add_argument("--retry-declined", action="store_true", help="ask again the questions declined before")
    ap.add_argument("--export", action="store_true")
    ap.add_argument("--import", dest="load", action="store_true")
    a = ap.parse_args()
    if a.export:                                   # reads the shadow only: no model, no GPU
        from aurora import kno_shadow
        from aurora.sol_reader import VaultReader
        rows = kno_shadow.export_seed(cfg, VaultReader(cfg))
        out = CONFIG / "shadow_seed.json"
        out.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"{len(rows)} seed answers with public sources -> {out} ({out.stat().st_size // 1024} KB)")
        return 0
    if a.load:
        r = httpx.post(f"{BASE}/v1/aurora/shadow/import", headers=HEAD, timeout=1800)
        print(r.status_code, r.text)
        return 0 if r.status_code == 200 else 1
    log = cfg.path("AURORA_STATUS_DIR") / "bench" / "shadow_seed.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    done = {}
    for line in log.read_text(encoding="utf-8").splitlines() if log.exists() else []:
        e = json.loads(line)
        done[e["question"]] = e
    want = {d.strip() for d in a.domains.split(",") if d.strip()}
    todo = [q for q in json.loads(Path(a.file).read_text(encoding="utf-8"))
            if (not want or q["domain"] in want)
            and (q["question"] not in done or a.retry_declined and done[q["question"]]["abstained"])]
    if a.limit:
        todo = todo[:a.limit]
    print(f"{len(todo)} questions to ask (~{len(todo) * 50 // 60} min); {len(done)} asked before")
    served = 0
    try:
        for i, q in enumerate(todo, 1):
            r = ask(q["question"])
            served += not r["abstained"]
            with log.open("a", encoding="utf-8") as f:
                f.write(json.dumps({**q, **r, "at": time.time()}, ensure_ascii=False) + "\n")
            mark = "❌" if r["error"] else "·" if r["abstained"] else "🌗"
            print(f"{i:3}/{len(todo)} {mark} {r['seconds']:5.1f} s  {r['sources']} src  [{q['domain']}] {q['question']}",
                  flush=True)
    except KeyboardInterrupt:
        print("\nstopped: the next run starts from here")
    print(f"answered with sources (in the shadow): {served}; declined: the vault has no sources for them yet")
    return 0


if __name__ == "__main__":
    sys.exit(main())
