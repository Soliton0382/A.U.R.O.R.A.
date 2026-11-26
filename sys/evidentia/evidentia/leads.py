# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Leads and their evidence (owner, 10 Nov: «stesso concetto delle shadows, un lavoro già fatto non lo ripetiamo… se
durante le investigazioni si aprono piste, si scatenano agenti investigativi che preparano il terreno, con messaggi
nella chat investigativa»).

A lead is a piece of work for one agent: «what» to chase, opened by a case (a client, an agent, the owner). The
registry is the archive's, not the case's: the same work — the same agent on the same target, said in other words
of the same letters — is done once; any later case that opens it is subscribed and gets the evidence already found,
at once. Each lead runs once through its agent, on the client's model (the server holds no model): a worker claims
it (a lease, so a crashed worker gives it back), works with the tools and reports. A report is checked here, line by
line: every piece of evidence names a document's page and quotes it, and the quote must be on that page — what the
page does not say is refused, never stored. The evidence lands as a message in every subscribed case's diary.

Limits so the autonomous work cannot run away: at most MAX_OPEN open leads per case, a lead born from a lead at most
MAX_DEPTH deep, a report at most MAX_EVIDENCE lines."""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
import unicodedata

from . import cases

STATUS = ("open", "working", "done", "cold", "dropped")      # cold: looked for, nothing found — also never redone
FINAL = ("done", "cold")
MAX_OPEN, MAX_DEPTH, MAX_EVIDENCE = 20, 3, 30
MAX_ACTIVE = 200          # open or working in the whole registry: cases are free to make, the work is not (audit, 10 Nov)
LEASE = 30 * 60
QUOTE_MIN, QUOTE_WORDS, QUOTE_MAX = 20, 4, 600     # measured after the spaces are flattened: «of      the» is not a quote

def _words(text: str) -> str:
    t = unicodedata.normalize("NFKC", str(text)).casefold()
    return " ".join(re.findall(r"\w+", t))


def key(agent: str, what: str) -> str:
    return hashlib.sha256(f"{agent}|{_words(what)}".encode()).hexdigest()[:32]


def _row(r) -> dict:
    d = dict(r)
    d.pop("lease_hash", None)                              # the lease's token never leaves the server
    for k in ("docs", "evidence"):
        d[k] = json.loads(d[k]) if d.get(k) else []
    return d


def get(con, lid: int) -> dict:
    r = con.execute("SELECT * FROM leads WHERE id = ?", (int(lid),)).fetchone()
    if r is None:
        raise KeyError(lid)
    out = _row(r)
    out["cases"] = [x[0] for x in con.execute("SELECT case_id FROM lead_cases WHERE lead = ? ORDER BY since", (lid,))]
    return out


def listing(con, status: str = "", case_id: str = "", limit: int = 100) -> list[dict]:
    q, args = "SELECT l.* FROM leads l", []
    where = []
    if case_id:
        q += " JOIN lead_cases c ON c.lead = l.id"
        where.append("c.case_id = ?")
        args.append(case_id)
    if status:
        where.append("l.status = ?")
        args.append(status)
    q += (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY l.id DESC LIMIT ?"
    return [_row(r) for r in con.execute(q, (*args, max(1, min(int(limit), 500))))]


def _post(con, lead: dict, case_id: str, reused: bool) -> None:
    """The evidence of a finished lead as a message in a case's chat (a step «evidence» of its diary)."""
    cases.step(con, case_id, "evidence",
               {"lead": lead["id"], "agent": lead["agent"], "what": lead["what"], "status": lead["status"],
                "summary": lead["summary"] or "", "evidence": lead["evidence"], "reused": reused},
               sorted({e["doc"] for e in lead["evidence"]}), commit=False)


def open_lead(con, case_id: str, what: str, agent: str, agents_known: set[str], why: str = "",
              docs: list[str] | None = None, parent: int | None = None) -> dict:
    """A lead opened by a case. The same work already in the registry is never opened again: the case is subscribed,
    and if the work is finished its evidence is posted in the case at once («reused»)."""
    cases.get(con, case_id)
    what = " ".join(str(what).split())[:400]
    if len(_words(what)) < 3:
        raise ValueError("what: say what to chase")
    if agent not in agents_known:
        raise ValueError(f"agent: one of {', '.join(sorted(agents_known))}")
    for d in docs or []:
        if not cases.DOC.fullmatch(str(d)):
            raise ValueError(f"a document is collection:number, not {d!r}")
    k, now = key(agent, what), time.time()
    old = con.execute("SELECT id FROM leads WHERE key = ?", (k,)).fetchone()
    if old:
        lead = get(con, old[0])
        fresh = case_id not in lead["cases"]
        if fresh:
            con.execute("INSERT INTO lead_cases(lead, case_id, since) VALUES (?,?,?)", (lead["id"], case_id, now))
            if lead["status"] in FINAL:
                _post(con, lead, case_id, reused=True)
            con.commit()                                   # the subscription and its message together
        return {**get(con, lead["id"]), "reused": True}
    depth = 0
    if parent is not None:
        depth = get(con, parent)["depth"] + 1
        if depth > MAX_DEPTH:
            raise ValueError(f"a lead born from leads at most {MAX_DEPTH} deep: report it instead")
    n_open = con.execute("SELECT COUNT(*) FROM leads l JOIN lead_cases c ON c.lead = l.id WHERE c.case_id = ? AND "
                         "l.status IN ('open', 'working')", (case_id,)).fetchone()[0]
    if n_open >= MAX_OPEN:
        raise ValueError(f"the case has {n_open} leads still open: let them finish first")
    if con.execute("SELECT COUNT(*) FROM leads WHERE status IN ('open', 'working')").fetchone()[0] >= MAX_ACTIVE:
        raise ValueError(f"{MAX_ACTIVE} leads are open in the whole archive: let them finish first")
    cur = con.execute("INSERT INTO leads(key, agent, what, why, docs, case_id, parent, depth, created) "
                      "VALUES (?,?,?,?,?,?,?,?,?)",
                      (k, agent, what, str(why)[:600], json.dumps(docs or []), case_id, parent, depth, now))
    con.execute("INSERT INTO lead_cases(lead, case_id, since) VALUES (?,?,?)", (cur.lastrowid, case_id, now))
    cases.step(con, case_id, "lead", {"lead": cur.lastrowid, "agent": agent, "what": what, "why": str(why)[:600]},
               docs or [], commit=False)
    con.commit()                                           # the lead, its case and its message together
    return {**get(con, cur.lastrowid), "reused": False}


def claim(con, worker: str, agent: str = "") -> dict | None:
    """The oldest open lead (or one whose worker's lease ran out), leased to this worker with a token: only who holds
    the token reports it (the worker's name is shown to everyone, so it proves nothing: audit, 10 Nov)."""
    worker = re.sub(r"[^\w.@-]", "", str(worker))[:60]
    if not worker:
        raise ValueError("worker: a name is needed")
    now = time.time()
    q = ("SELECT id FROM leads WHERE (status = 'open' OR (status = 'working' AND lease_until < ?))" +
         (" AND agent = ?" if agent else "") + " ORDER BY depth, id LIMIT 1")
    r = con.execute(q, (now, agent) if agent else (now,)).fetchone()
    if r is None:
        return None
    token = secrets.token_urlsafe(18)
    cur = con.execute("UPDATE leads SET status = 'working', worker = ?, lease_until = ?, lease_hash = ? WHERE id = ? AND "
                      "(status = 'open' OR (status = 'working' AND lease_until < ?))",
                      (worker, now + LEASE, _hash(token), r[0], now))
    con.commit()
    if cur.rowcount != 1:                                  # taken by another worker meanwhile
        return None
    return {**get(con, r[0]), "token": token}


def _hash(token: str) -> str:
    return hashlib.sha256(str(token).encode()).hexdigest()


QUOTES = str.maketrans({"‘": "'", "’": "'", "‛": "'", "`": "'", "´": "'", "“": '"', "”": '"', "„": '"'})


def _flat_map(text: str) -> tuple[str, list[int]]:
    """The text as a quote is compared (NFKC, case folded, the typographic quotes plain, the spaces flattened) and,
    for each of its characters, the place in the text it comes from: what matched is saved as the page writes it."""
    out, where, gap = [], [], True
    for i, ch in enumerate(str(text)):
        for c in unicodedata.normalize("NFKC", ch).casefold().translate(QUOTES):
            if c.isspace():
                if not gap:
                    out.append(" ")
                    where.append(i)
                gap = True
            else:
                out.append(c)
                where.append(i)
                gap = False
    if out and out[-1] == " ":
        out.pop()
        where.pop()
    return "".join(out), where


def _flat(text: str) -> str:
    return _flat_map(text)[0]


def _on_page(page_text: str, flat_quote: str) -> str | None:
    """The stretch of the page the quote matches, in the page's own characters — never the model's (audit E2, B17:
    «1000⁰» matched «10000» and was saved as the model wrote it)."""
    flat, where = _flat_map(page_text)
    at = flat.find(flat_quote)
    if at < 0:
        return None
    return page_text[where[at]:where[at + len(flat_quote) - 1] + 1]


def check(corpus, evidence: list, mask=None) -> tuple[list[dict], list[dict]]:
    """Each line of evidence on its page: kept with its citation, or refused with the reason. With `mask` the page is
    read as the agents saw it, protected names masked (F5, B24): what is kept never holds one."""
    mask = mask or (lambda t: t)
    from . import search
    kept, refused = [], []
    for e in evidence[:MAX_EVIDENCE] if isinstance(evidence, list) else []:
        e = e if isinstance(e, dict) else {}
        doc, quote, note = str(e.get("doc", "")), str(e.get("quote", "")).strip(), str(e.get("note", ""))[:400]
        if len(quote) > 2 * QUOTE_MAX:                    # 50,000 characters are not a quote: refused unread (B17)
            refused.append({"doc": doc, "page": e.get("page"), "quote": quote[:80] + "…",
                            "why": f"quote: at most {QUOTE_MAX} characters"})
            continue
        try:
            n = int(e.get("page"))
        except (TypeError, ValueError):
            refused.append({**e, "why": "page: a number"})
            continue
        flat = _flat(quote)
        words = re.findall(r"\w+", flat)
        if not (QUOTE_MIN <= len(flat) <= QUOTE_MAX and len(words) >= QUOTE_WORDS and
                any(len(w) >= 5 or any(ch.isdigit() for ch in w) for w in words)):
            refused.append({**e, "why": f"quote: {QUOTE_WORDS} words or more ({QUOTE_MIN}–{QUOTE_MAX} characters), "
                                        "copied from the page, not only common words"})
            continue
        p = search.page(corpus, doc, n) if cases.DOC.fullmatch(doc) else None
        held = None if p is None else _on_page(mask(p["text"] or ""), flat)
        if p is None:
            refused.append({**e, "why": "no such page"})
        elif held is None:
            refused.append({**e, "why": "the page does not say these words"})
        else:
            kept.append({"doc": doc, "page": n, "quote": held, "note": note, "cite": p["cite"]})
    if isinstance(evidence, list) and len(evidence) > MAX_EVIDENCE:
        refused.append({"why": f"at most {MAX_EVIDENCE} lines: the rest not read"})
    return kept, refused


def report(con, corpus, lid: int, token: str, status: str, summary: str, evidence: list, mask=None) -> dict:
    """A worker's result: the evidence checked on the pages, the lead closed, the evidence posted in every case
    subscribed to it. «done» needs at least one line that holds; «cold» says what was looked for and not found."""
    held = con.execute("SELECT status, lease_hash FROM leads WHERE id = ?", (int(lid),)).fetchone()
    if held is None:
        raise KeyError(lid)
    if held["status"] != "working" or not token or held["lease_hash"] != _hash(token):
        raise PermissionError("this lead is not leased to you (claim it first; report it with its token)")
    if status not in FINAL:
        raise ValueError(f"status: one of {', '.join(FINAL)}")
    summary = str(summary).strip()[:4000]
    if len(summary) < 20:
        raise ValueError("summary: what was found, or what was looked for and not found")
    kept, refused = check(corpus, evidence, mask)
    if status == "done" and not kept:
        raise LookupError(json.dumps({"detail": "no line of evidence holds on its page", "refused": refused}))
    cur = con.execute("UPDATE leads SET status = ?, summary = ?, evidence = ?, finished = ?, lease_until = NULL, "
                      "lease_hash = NULL WHERE id = ? AND status = 'working' AND lease_hash = ?",
                      (status, summary, json.dumps(kept, ensure_ascii=False), time.time(), lid, _hash(token)))
    if cur.rowcount != 1:                                 # the lease changed hands while the pages were checked (B28)
        con.rollback()
        raise PermissionError("this lead is not leased to you any more (its lease ran out and another worker took it)")
    lead = get(con, lid)
    for case_id in lead["cases"]:
        try:
            _post(con, lead, case_id, reused=case_id != lead["case_id"])
        except KeyError:                                  # a subscribed case since deleted: nothing to post to
            pass
    con.commit()                                          # the lead closed and its messages posted, or nothing
    return {**lead, "refused": refused}


def drop(con, lid: int, why: str) -> dict:
    """The owner drops a lead not worth chasing (never one already finished: its evidence stays)."""
    lead = get(con, lid)
    if lead["status"] in FINAL:
        raise ValueError("a finished lead stays")
    con.execute("UPDATE leads SET status = 'dropped', summary = ?, finished = ? WHERE id = ?",
                (str(why)[:400], time.time(), lid))
    con.commit()
    return get(con, lid)


def reopen(con, lid: int, why: str) -> dict:
    """The owner opens again a lead closed «cold» or «dropped» (audit E5, B20: a worker led astray closed it with
    twenty characters, and the same work was never chased again). Only from the owner's page — no tool of the agents
    reaches it. What it was closed with goes into every case subscribed to it, then the lead waits in the queue again.
    A «done» lead stays: its evidence was checked on its pages."""
    lead = get(con, lid)
    if lead["status"] not in ("cold", "dropped"):
        raise ValueError("only a cold or dropped lead is opened again")
    why = " ".join(str(why).split())[:400]
    for case_id in lead["cases"]:
        try:
            cases.step(con, case_id, "note", {"text": f"↩️ lead #{lead['id']} reopened by the owner"
                                                       + (f": {why}" if why else "")
                                                       + f" — it was {lead['status']} ({lead.get('worker') or 'owner'}): "
                                                       + (lead.get("summary") or "")[:300]}, commit=False)
        except KeyError:                                  # a subscribed case since deleted
            pass
    con.execute("UPDATE leads SET status = 'open', summary = NULL, finished = NULL, worker = NULL, lease_until = NULL, "
                "lease_hash = NULL WHERE id = ? AND status IN ('cold', 'dropped')", (int(lid),))
    con.commit()                                          # the lead open again and its notes, or nothing
    return get(con, lid)


REPORT = """
WHEN YOU ARE DONE, report with report_lead and the lead's token: status «done» with the evidence (each line: doc,
page, quote — at least four words copied exactly from that page — and a note of what it shows) or «cold» with what you looked for and did not find.
A quote the page does not hold is refused. New leads you meet: open them with open_lead (parent: this lead), never
chase them here.
"""
