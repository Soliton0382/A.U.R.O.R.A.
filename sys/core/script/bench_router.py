#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Where the router errs (owner, 2026-10-13: «cerchiamo di capire dove il router sbaglia di più… percorsi logici per
il routing delle operazioni precisi almeno al 99%»). Each decision measured on its own, on the owner's real messages
(the conversation memory: each with the two turns before it, as the chat had them) and on benchmark questions:

    tools   a connected service (the agent and its plugins) or knowledge — core_route.wants_tools
    self    about Aurora herself (her state, her memories, small talk) or about the world — Pipeline._route
    kind    fact, explain, case or solve — kno_read.kind (the order of the sources: kno_think)

against a reference written by Claude through the masking (sec_mask: what leaves is masked, the owner's messages
included). Local models only for the router; the reference is one short cloud call a message.

    python script/bench_router.py [--chat 150] [--bench 50] [--judge sonnet]
    python script/bench_router.py --replay <router-….json>   (the same messages and references, no cloud: a change checked)
Results: <STATUS>/bench/router-<time>.json and a table: each decision's accuracy and its errors by kind.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from aurora.api import core  # noqa: E402,F401  — core first: core_route imports it
from aurora.api import core_route  # noqa: E402

from aurora import kno_read, sys_config  # noqa: E402

REF = ("You label how an assistant should handle the owner's LAST MESSAGE (with the turns before it as context). The "
       "assistant, Aurora, has a library of knowledge and these CONNECTED SERVICES:\n{services}\n"
       "Answer three questions:\n"
       "route — «tools» when the message needs one of the connected services (to read or do something there: the "
       "house, the calendar, e-mail, the firewall, files, routines, the social pages…); «self» when it is about Aurora "
       "herself (how she is, what she remembers of the owner, small talk, a greeting); «knowledge» for any question about "
       "the world.\n"
       "kind — only for knowledge: «fact» (a fact to look up: who, when, how many, a name, a date, news), «explain» (a "
       "concept, how or why something works, a comparison), «case» (a personal situation with problems, asking what to "
       "do), «solve» (a calculation, a puzzle, an exercise or quiz with options, code); «none» otherwise.\n"
       "Reply with JSON only: {{\"route\": \"…\", \"kind\": \"…\"}}")


def chat_messages(p, n: int, seed: int = 7) -> list[dict]:
    turns = p.reader.recent(3000)
    out = []
    for i, t in enumerate(turns):
        if t.extra.get("role") != "user" or len(t.text) < 6:
            continue
        q = t.text.split(" [")[0].strip()
        out.append({"question": q, "recent": turns[max(0, i - 2):i], "origin": "chat"})
    seen, uniq = set(), []
    for x in out:
        if x["question"].lower() not in seen:
            seen.add(x["question"].lower())
            uniq.append(x)
    random.Random(seed).shuffle(uniq)
    return uniq[:n]


def bench_messages(n: int) -> list[dict]:
    import bench_public as P
    sets = ["aurora_edge", "simpleqa", "math500", "truthfulqa", "mmlu_pro"]
    items = [it["prompt"] for s in sets for it in P.questions(s, 10)]
    random.Random(7).shuffle(items)
    return [{"question": q, "recent": [], "origin": "bench"} for q in items[:n]]


def reference(judge, services: str, m: dict) -> dict:
    prev = "\n".join(f"{'Owner' if t.extra.get('role') == 'user' else 'Aurora'}: {t.text[:300]}" for t in m["recent"])
    out = judge.complete(REF.format(services=services), (f"TURNS BEFORE:\n{prev}\n\n" if prev else "")
                         + f"LAST MESSAGE: {m['question'][:1500]}", 40).answer
    g = re.search(r"\{.*\}", out, re.S)
    try:
        d = json.loads(g.group(0)) if g else {}
    except ValueError:
        d = {}
    return {"route": str(d.get("route", "?")).lower(), "kind": str(d.get("kind", "none")).lower()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chat", type=int, default=150)
    ap.add_argument("--bench", type=int, default=50)
    ap.add_argument("--judge", default="sonnet")
    ap.add_argument("--replay", help="a previous result: its messages and references again, the router decided anew")
    a = ap.parse_args()
    cfg = sys_config.get()
    p = core.pipeline()
    from aurora import mdl_router
    from aurora.mdl_cloud import ClaudeCodeLLM
    judge = mdl_router.MaskedLLM(ClaudeCodeLLM(cfg, a.judge), "service", cfg)       # the owner's words masked
    services = "\n".join(core_route.connected_services())
    if a.replay:                                       # the turns before: the chat's, found again by the question
        old = json.loads(Path(a.replay).read_text(encoding="utf-8"))["rows"]
        full = {m["question"][:300]: m for m in chat_messages(p, 100000) + bench_messages(len(old))}
        msgs = [{**full.get(r["question"], {"recent": [], "question": r["question"]}), "origin": r["origin"],
                 "ref": r["ref"]} for r in old]
    else:
        msgs = chat_messages(p, a.chat) + bench_messages(a.bench)
    rows, t0 = [], time.time()
    for i, m in enumerate(msgs, 1):
        ref = m.get("ref") or reference(judge, services, m)
        tools = core_route.wants_tools(m["question"], m["recent"])
        is_self = not tools and p._route(m["question"], m["recent"]) == "self"
        route = "tools" if tools else "self" if is_self else "knowledge"
        kind = kno_read.kind(p, m["question"]) if route == "knowledge" else "none"
        row = {"origin": m["origin"], "question": m["question"][:300], "ref": ref, "route": route, "kind": kind}
        rows.append(row)
        ok_r = route == ref["route"]
        ok_k = ref["route"] != "knowledge" or route != "knowledge" or kind == ref["kind"]
        print(f"{i:4}/{len(msgs)} {m['origin']:5} route {route:9} ref {ref['route']:9} {'✓' if ok_r else '✗'} "
              f"kind {kind:7} ref {ref['kind']:7} {'✓' if ok_k else '✗'} {m['question'][:50]!r}", flush=True)
    both = [r for r in rows if r["route"] == "knowledge" and r["ref"]["route"] == "knowledge"]
    summary = {
        "messages": len(rows),
        "route_right": sum(r["route"] == r["ref"]["route"] for r in rows),
        "route_errors": Counter(f"{r['ref']['route']} → {r['route']}" for r in rows if r["route"] != r["ref"]["route"]).most_common(),
        "kind_compared": len(both), "kind_right": sum(r["kind"] == r["ref"]["kind"] for r in both),
        "kind_errors": Counter(f"{r['ref']['kind']} → {r['kind']}" for r in both if r["kind"] != r["ref"]["kind"]).most_common(),
        "by_origin": {o: {"n": sum(r["origin"] == o for r in rows),
                          "route_right": sum(r["origin"] == o and r["route"] == r["ref"]["route"] for r in rows)}
                      for o in ("chat", "bench")},
        "minutes": round((time.time() - t0) / 60, 1)}
    out = cfg.path("AURORA_STATUS_DIR") / "bench" / f"router-{datetime.now():%Y%m%d-%H%M}.json"
    out.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print("→", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
