#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Score Evidentia on the invented law-office corpus against the frozen key (../chiave/chiave.json).

  server  the archive alone (no model): retrieval of the gold page, isolation between matters, Italian inflections
  llm     Evidentia + a client model (Aurora's local reasoner, an OpenAI-style endpoint): the legal agents' cards as
          prompts, a tool loop with only search / read_page, every citation checked on its page by leads.check

Usage (Evidentia's venv, EVD_ENV_FILE=../evd.env):
  python -I valuta.py server
  python -I valuta.py llm [--only a1,b_A,...] [--url http://127.0.0.1:9711]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVD = ROOT.parents[1] / "sys" / "core"
sys.path.insert(0, str(EVD))
from evidentia import agents, config, leads, search, store  # noqa: E402

KEY = ROOT / "chiave" / "chiave.json"
OUT = ROOT / "risultati"
MATTER_NAME = {"A": "Ferri Meccanica S.r.l. contro Lumen Impianti S.p.A. (fornitura, contratto 2025/114)",
               "B": "Giorgio Rinaldi contro Alfa Logistica S.r.l. (licenziamento)",
               "C": "Condominio Via dei Tigli 18, Verona (infiltrazioni, delibera del 12 maggio 2025)"}


def key() -> dict:
    data = KEY.read_bytes()
    frozen = (ROOT / "chiave" / "chiave.sha256").read_text().split()[0]
    if hashlib.sha256(data).hexdigest() != frozen:
        raise SystemExit("the key changed after it was frozen: stop")
    return json.loads(data)


def matter_of(doc: str) -> str:
    stem = doc.split(":", 1)[-1]
    return stem[:1]


def norm(t: str) -> str:
    return " ".join(str(t).casefold().replace("’", "'").split())


def has(text: str, groups) -> list[bool]:
    t = norm(text)
    return [any(norm(alt) in t for alt in g) for g in groups]


# ---------------------------------------------------------------------------------------------------------- server
def server(k: dict, corpus) -> dict:
    out = {"lookup": [], "isolation": [], "italian": []}
    for qid, m, q, _ans, gold in k["lookup"]:
        r = search.ask(corpus, q, limit=20)
        hits = [h["doc"].split(":", 1)[1] + f"#{h['page']}" for h in r["hits"]]
        golds = [f"{s}#{p}" for s, p in gold]
        rank = next((i + 1 for i, h in enumerate(hits) if h in golds), None)
        others = sum(1 for h in r["hits"] if matter_of(h["doc"]) != m)
        out["lookup"].append({"id": qid, "matter": m, "mode": r["mode"], "used": r["used"], "rank": rank,
                              "hits": len(hits), "other_matter_hits": others, "top5": hits[:5]})
    for gid, m, q in k["isolation"]:
        r = search.ask(corpus, q, limit=20)
        by = {}
        for h in r["hits"]:
            by[matter_of(h["doc"])] = by.get(matter_of(h["doc"]), 0) + 1
        out["isolation"].append({"id": gid, "matter": m, "q": q, "hits": len(r["hits"]), "by_matter": by,
                                 "leak": sum(v for kk, v in by.items() if kk != m)})
    for iid, a, b, gold in k["italian"]:
        row = {"id": iid, "forms": [a, b], "gold": gold}
        for w in (a, b):
            hits = [h["doc"].split(":", 1)[1] for h in search.search(corpus, w, limit=50)]
            row[w] = gold in hits
        out["italian"].append(row)
    n = len(out["lookup"])
    out["score"] = {
        "lookup_recall@1": sum(1 for r in out["lookup"] if r["rank"] == 1) / n,
        "lookup_recall@5": sum(1 for r in out["lookup"] if r["rank"] and r["rank"] <= 5) / n,
        "lookup_recall@20": sum(1 for r in out["lookup"] if r["rank"]) / n,
        "lookup_hits_from_other_matters": sum(r["other_matter_hits"] for r in out["lookup"]) /
                                          max(1, sum(r["hits"] for r in out["lookup"])),
        "isolation_leaks": sum(r["leak"] for r in out["isolation"]),
        "isolation_hits": sum(r["hits"] for r in out["isolation"]),
        "italian_both_forms_found": sum(1 for r in out["italian"] if all(r[w] for w in r["forms"])) / len(out["italian"]),
    }
    return out


# ------------------------------------------------------------------------------------------------------------- llm
TOOLS = """You have two tools on the document server and nothing else. Reply with ONE JSON object per turn, no prose:
  {"action": "search", "q": "words to look for"}            full-text search; hits with document, page, snippet
  {"action": "read", "doc": "OTHER:<name>", "page": N}         the whole text of one page
  {"action": "answer", "risposta": "...in italiano...", "citazioni": [{"doc": "OTHER:<name>", "page": N, "quote": "words copied from the page"}]}
Every fact in the answer needs a citation whose quote is copied word for word from the page (at least 4 words).
Search with the words the documents use (they are Italian). Read a page before quoting it. At most %d turns."""


def llm_call(url: str, messages: list[dict], max_tokens: int = 1800) -> str:
    for _ in range(120):                                  # never take both slots from the owner: wait for a free one
        try:
            slots = json.loads(urllib.request.urlopen(f"{url}/slots", timeout=10).read())
            if sum(1 for s in slots if s.get("is_processing")) < len(slots):
                break
        except Exception:  # noqa: BLE001
            break
        time.sleep(5)
    body = {"messages": messages, "temperature": 0, "max_tokens": max_tokens,
            "chat_template_kwargs": {"enable_thinking": False}}
    req = urllib.request.Request(f"{url}/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=900).read())
    return r["choices"][0]["message"]["content"] or ""


def first_json(text: str) -> dict | None:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    depth, start = 0, None
    for i, ch in enumerate(text):
        if ch == "{":
            depth += 1
            start = i if start is None else start
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    start = None
    return None


def run_agent(url: str, corpus, card: dict, goal: str, turns: int) -> dict:
    sys_prompt = agents.prompt(card, goal) + "\n" + TOOLS % turns + "\nThe reader is an Italian lawyer: answer in Italian."
    msgs = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": goal}]
    trace, t0 = [], time.time()
    context_full = False
    for turn in range(turns):
        try:
            reply = llm_call(url, msgs)
        except urllib.error.HTTPError as e:          # v2b: the slot's context (32k) is full — said, then answer
            if e.code != 400:
                raise
            context_full = True
            for m in msgs[2:-6]:
                if m["role"] == "user":
                    m["content"] = "(observation omitted: context full)"
            trace.append({"context_full_at_turn": turn})
            break
        act = first_json(reply) or {}
        msgs.append({"role": "assistant", "content": reply})
        a = act.get("action")
        if a == "answer" or turn == turns - 1 and a not in ("search", "read") and not FORCE_FINAL:
            return {"answer": act, "turns": turn + 1, "trace": trace, "seconds": round(time.time() - t0, 1)}
        if a == "search":
            r = search.ask(corpus, str(act.get("q", ""))[:300], limit=10)
            res = [{"doc": h["doc"], "page": h["page"], "snippet": h["snippet"]} for h in r["hits"]]
            trace.append({"search": act.get("q"), "hits": [f"{h['doc']}#{h['page']}" for h in res]})
            obs = json.dumps({"used": r["used"], "total": r["total"], "hits": res}, ensure_ascii=False)
        elif a == "read":
            p = search.page(corpus, str(act.get("doc", "")), int(act.get("page") or 0)) if str(act.get("page", "")).isdigit() \
                or isinstance(act.get("page"), int) else None
            trace.append({"read": f"{act.get('doc')}#{act.get('page')}", "found": bool(p)})
            obs = json.dumps({"doc": act.get("doc"), "page": act.get("page"),
                              "text": (p or {}).get("text") or "(no text on this page: it may be a scan)"}
                             if p else {"error": "no such page"}, ensure_ascii=False)
        else:
            obs = '{"error": "reply with one JSON object: search, read or answer"}'
            trace.append({"bad_reply": reply[:200]})
        if turn == turns - 2:
            obs += "\nLAST TURN: answer now with the JSON answer object."
        msgs.append({"role": "user", "content": obs})
    if FORCE_FINAL:                       # v2 (amended after run 1, said in the report): one last call, tools closed
        msgs.append({"role": "user", "content": "No more tools. Reply now with the JSON answer object only, from what "
                                                "you have read; say what you did not find."})
        try:
            raw = llm_call(url, msgs, max_tokens=4000)
        except urllib.error.HTTPError:
            return {"answer": {}, "turns": turns, "context_full": True, "trace": trace, "seconds": round(time.time() - t0, 1)}
        act = first_json(raw) or {"risposta": raw, "citazioni": [], "unparsed": True}   # v2b: prose kept, no citations
        return {"answer": act, "turns": turns + 1, "context_full": context_full, "trace": trace, "seconds": round(time.time() - t0, 1), "forced": True}
    return {"answer": {}, "turns": turns, "trace": trace, "seconds": round(time.time() - t0, 1)}


FORCE_FINAL = False


def score_cites(corpus, ans: dict, matter: str) -> dict:
    cites = ans.get("citazioni") or []
    cites = [c for c in cites if isinstance(c, dict)]
    kept, refused = leads.check(corpus, cites)
    fake = [r for r in refused if r.get("why") in ("no such page", "the page does not say these words")]
    return {"n": len(cites), "kept": len(kept), "fake": len(fake), "format": len(refused) - len(fake),
            "kept_pages": [f"{c['doc'].split(':', 1)[1]}#{c['page']}" for c in kept],
            "other_matter": sum(1 for c in kept if matter_of(c["doc"]) != matter)}


def tasks(k: dict) -> list[dict]:
    t = []
    for qid, m, q, ans, gold in k["lookup"]:
        t.append({"id": qid, "kind": "lookup", "matter": m, "card": "document_reviewer", "turns": 6,
                  "goal": f"Pratica: {MATTER_NAME[m]}.\nDomanda dell'avvocato: {q}", "ans": ans,
                  "gold": [f"{s}#{p}" for s, p in gold]})
    for m in "ABC":
        t.append({"id": f"b_{m}", "kind": "chrono", "matter": m, "card": "chronologist", "turns": 12,
                  "goal": f"Pratica: {MATTER_NAME[m]}.\nRicostruisci la cronologia completa dei fatti della pratica, "
                          "ogni evento con la sua data e la fonte.", "events": k["chrono"][m]})
        t.append({"id": f"c_{m}", "kind": "contra", "matter": m, "card": "contradictions", "turns": 12,
                  "goal": f"Pratica: {MATTER_NAME[m]}.\nTrova le contraddizioni tra i documenti della pratica (date, "
                          "importi, fatti): per ognuna i due lati con le fonti.", "contra": k["contra"][m]})
        t.append({"id": f"d_{m}", "kind": "deadline", "matter": m, "card": "deadlines", "turns": 12,
                  "goal": f"Pratica: {MATTER_NAME[m]}.\nElenca i termini e le scadenze da rispettare in questa pratica, "
                          "ognuno con la data, come è calcolato e la fonte.",
                  "dl": [d for d in k["deadlines"] if d[1] == m]})
        t.append({"id": f"e_{m}", "kind": "summary", "matter": m, "card": "drafter", "turns": 12,
                  "goal": f"Pratica: {MATTER_NAME[m]}.\nScrivi per il cliente un riassunto chiaro della situazione "
                          "(massimo 250 parole), con le fonti.", "points": k["summary"][m]})
    for fid, m, stmt, labels in k["classify"]:
        t.append({"id": fid, "kind": "classify", "matter": m, "card": "verifier", "turns": 6,
                  "goal": f"Pratica: {MATTER_NAME[m]}.\nQuesta affermazione è un FATTO documentato, una TESTIMONIANZA o "
                          f"un'ACCUSA? Rispondi con una di queste tre parole all'inizio, poi spiega con le fonti.\n"
                          f"Affermazione: «{stmt}»", "labels": labels})
    return t


def score(task: dict, run: dict, corpus) -> dict:
    ans = run["answer"] if isinstance(run["answer"], dict) else {}
    text = str(ans.get("risposta", ""))
    c = score_cites(corpus, ans, task["matter"])
    s = {"id": task["id"], "kind": task["kind"], "matter": task["matter"], "turns": run["turns"],
         "seconds": run["seconds"], "answered": bool(text), "cites": c}
    if task["kind"] == "lookup":
        s["correct"] = all(has(text, task["ans"]))
        s["gold_cited"] = any(p in task["gold"] for p in c["kept_pages"])
    elif task["kind"] == "chrono":
        got = [any(norm(d) in norm(text) or norm(d.replace(" 2025", "")) in norm(text) for _ in [0]) for d, _ in task["events"]]
        s["share"] = sum(got) / len(got)
        s["missing"] = [d for (d, _), g in zip(task["events"], got) if not g]
    elif task["kind"] == "contra":
        found = [all(has(text, groups)) for _, _, groups in task["contra"]]
        s["share"] = sum(found) / len(found)
        s["found"] = [cid for (cid, _, _), f in zip(task["contra"], found) if f]
    elif task["kind"] == "deadline":
        ok = [any(norm(a) in norm(text) for a in d[3]) for d in task["dl"]]
        s["share"] = sum(ok) / len(ok)
        s["found"] = [d[0] for d, o in zip(task["dl"], ok) if o]
    elif task["kind"] == "summary":
        got = has(text, task["points"])
        s["share"] = sum(got) / len(got)
        s["words"] = len(text.split())
    elif task["kind"] == "classify":
        head = norm(text)[:60]
        lab = next((w for w in ("fatto", "testimonianza", "accusa") if w in head), None)
        s["label"], s["correct"] = lab, lab in task["labels"]
    return s


def llm(k: dict, corpus, url: str, only: set[str] | None) -> dict:
    cards = {c["name"]: c for c in agents.load(EVD.parents[1] / "sys" / "agents")}
    OUT.mkdir(exist_ok=True)
    log = OUT / ("llm_runs_v2b.jsonl" if FORCE_FINAL else "llm_runs.jsonl")
    done = {}
    if log.is_file():
        for line in log.read_text().splitlines():
            r = json.loads(line)
            done[r["task"]["id"]] = r
    for task in tasks(k):
        if only and task["id"] not in only or task["id"] in done:
            continue
        turns = task["turns"] * 2 if FORCE_FINAL and task["turns"] > 6 else task["turns"]   # v2: 24, Aurora's chat has 30
        run = run_agent(url, corpus, cards[task["card"]], task["goal"], turns)
        rec = {"task": task, "run": run, "score": score(task, run, corpus)}
        with log.open("a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        done[task["id"]] = rec
        print(json.dumps(rec["score"], ensure_ascii=False), flush=True)
    return done


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["server", "llm"])
    ap.add_argument("--only", default="")
    ap.add_argument("--url", default="http://127.0.0.1:9711")
    ap.add_argument("--v2", action="store_true", help="24 turns for the matter tasks and a forced final answer")
    a = ap.parse_args()
    global FORCE_FINAL
    FORCE_FINAL = a.v2
    k = key()
    cfg = config.load()
    corpus = store.connect(cfg.path("EVD_DATA_DIR"), "corpus.db", readonly=True)
    OUT.mkdir(exist_ok=True)
    if a.mode == "server":
        r = server(k, corpus)
        (OUT / "server.json").write_text(json.dumps(r, indent=1, ensure_ascii=False))
        print(json.dumps(r["score"], indent=1))
    else:
        llm(k, corpus, a.url, set(a.only.split(",")) if a.only else None)


if __name__ == "__main__":
    main()
