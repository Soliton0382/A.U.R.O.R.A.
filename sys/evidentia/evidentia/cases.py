# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The case files (owner, 9 Nov: «ogni chat è un fascicolo e i fascicoli stanno negli archivi»): one per investigation,
its diary of steps (every search, read, claim, relation, lead, answer — a step done is never redone), its table (what
the model sees at each step: the goal, the open points, the evidence in hand, the leads), its group (by similarity of
the investigations, filled in once the embeddings exist). Reopening a case resumes it exactly where it stopped."""
from __future__ import annotations

import json
import re
import secrets
import time

DOC = re.compile(r"[A-Z][A-Z0-9-]*:[^\x00-\x1f]{1,200}")     # collection:number (OTHER keeps a file's stem)
KINDS = ("question", "plan", "search", "read", "claim", "relation", "lead", "evidence", "answer", "note")


def _title(t: str) -> str:
    t = " ".join(str(t).split())[:120]
    if not t:
        raise ValueError("a title is needed")
    return t


def create(con, title: str) -> dict:
    cid, now = secrets.token_hex(6), time.time()
    con.execute("INSERT INTO cases(id, title, created, updated) VALUES (?,?,?,?)", (cid, _title(title), now, now))
    con.execute("INSERT INTO tables(case_id, goal, open_points, evidence, leads) VALUES (?, '', '[]', '[]', '[]')", (cid,))
    con.commit()
    return get(con, cid)


def get(con, cid: str) -> dict:
    r = con.execute("SELECT * FROM cases WHERE id = ?", (cid,)).fetchone()
    if r is None:
        raise KeyError(cid)
    n = con.execute("SELECT COUNT(*) FROM steps WHERE case_id = ?", (cid,)).fetchone()[0]
    return {**dict(r), "steps": n}


def listing(con) -> list[dict]:
    """Every case, newest first, with its group: the explorer's view."""
    rows = con.execute("SELECT c.*, (SELECT COUNT(*) FROM steps s WHERE s.case_id = c.id) AS steps FROM cases c "
                       "WHERE archived = 0 ORDER BY updated DESC").fetchall()
    return [dict(r) for r in rows]


def rename(con, cid: str, title: str) -> dict:
    get(con, cid)
    con.execute("UPDATE cases SET title = ?, updated = ? WHERE id = ?", (_title(title), time.time(), cid))
    con.commit()
    return get(con, cid)


def move(con, cid: str, group: str) -> dict:
    """The case into a folder of the Finder (owner, 10 Nov: «menù stile Finder così restano ordinate ed impilate»);
    an empty name takes it out of any folder."""
    get(con, cid)
    g = " ".join(str(group).split())[:60] or None
    con.execute("UPDATE cases SET grp = ?, updated = ? WHERE id = ?", (g, time.time(), cid))
    con.commit()
    return get(con, cid)


def delete(con, cid: str) -> bool:
    """The case and its diary gone (owner, 9 Nov: «eliminazione di uno slot chat»); the relations it found stay in the
    global registry — they are the archive's, not the case's."""
    get(con, cid)
    for t in ("steps", "tables", "lead_cases", "cases"):           # the leads stay: the archive's work, not the case's
        con.execute(f"DELETE FROM {t} WHERE {'id' if t == 'cases' else 'case_id'} = ?", (cid,))
    con.commit()
    return True


def step(con, cid: str, kind: str, content: dict, docs: list[str] | None = None, commit: bool = True) -> int:
    if kind not in KINDS:
        raise ValueError(f"kind: one of {KINDS}")
    get(con, cid)
    for d in docs or []:
        if not DOC.fullmatch(str(d)):
            raise ValueError(f"a document is collection:number, not {d!r}")
    cur = con.execute("INSERT INTO steps(case_id, at, kind, content, docs) VALUES (?,?,?,?,?)",
                      (cid, time.time(), kind, json.dumps(content, ensure_ascii=False), json.dumps(docs or [])))
    con.execute("UPDATE cases SET updated = ? WHERE id = ?", (time.time(), cid))
    if commit:
        con.commit()
    return cur.lastrowid


def diary(con, cid: str, since: int = 0) -> list[dict]:
    get(con, cid)
    return [{**dict(r), "content": json.loads(r["content"]), "docs": json.loads(r["docs"] or "[]")}
            for r in con.execute("SELECT * FROM steps WHERE case_id = ? AND id > ? ORDER BY id", (cid, since))]


def done_before(con, cid: str, kind: str, content: dict) -> bool:
    """A step already in the diary (the same search, the same document read): never redone."""
    key = json.dumps(content, ensure_ascii=False)
    return con.execute("SELECT 1 FROM steps WHERE case_id = ? AND kind = ? AND content = ? LIMIT 1",
                       (cid, kind, key)).fetchone() is not None


def table(con, cid: str) -> dict:
    r = con.execute("SELECT * FROM tables WHERE case_id = ?", (cid,)).fetchone()
    if r is None:
        raise KeyError(cid)
    return {"goal": r["goal"], **{k: json.loads(r[k] or "[]") for k in ("open_points", "evidence", "leads")}}


def set_table(con, cid: str, **parts) -> dict:
    cur = table(con, cid)
    cur.update({k: v for k, v in parts.items() if k in cur})
    con.execute("UPDATE tables SET goal = ?, open_points = ?, evidence = ?, leads = ? WHERE case_id = ?",
                (cur["goal"], json.dumps(cur["open_points"]), json.dumps(cur["evidence"]), json.dumps(cur["leads"]), cid))
    con.commit()
    return cur


HEADS = {"question": "❓ Domanda", "answer": "🕵️ Risposta", "search": "🔎 Ricerca", "lead": "🧭 Pista",
         "evidence": "🧾 Evidenze", "note": "📝 Nota", "read": "📄 Lettura", "claim": "✅ Affermazione",
         "relation": "🔗 Relazione", "plan": "🗺️ Piano"}


def _sources(docs: list[str], most: int = 12) -> str:
    names = [d.split(":", 1)[-1] for d in docs]
    more = f" e altre {len(names) - most}" if len(names) > most else ""
    return ", ".join(names[:most]) + more


def markdown(con, cid: str) -> str:
    """The case as a document (the «export» and the PDF, owner 10 Nov: «PDF ben formattato»): a head with its numbers,
    then every step under its own heading, every quote with its source, the sources written short."""
    c, steps = get(con, cid), diary(con, cid)
    kinds = {}
    for s in steps:
        kinds[s["kind"]] = kinds.get(s["kind"], 0) + 1
    out = [f"# {c['title']}\n",
           f"*Fascicolo {cid} · aperto il {time.strftime('%d/%m/%Y', time.localtime(c['created']))} · "
           f"{len(steps)} passi: " + ", ".join(f"{HEADS.get(k, k)} {n}" for k, n in kinds.items()) + "*\n"]
    for s in steps:
        when = time.strftime("%d/%m/%Y", time.localtime(s["at"]))
        out.append(f"## {HEADS.get(s['kind'], s['kind'])} · {when}\n\n{_body(s['kind'], s['content'])}\n" +
                   (f"\n*Fonti: {_sources(s['docs'])}*\n" if s["docs"] else ""))
    return "\n".join(out)


def _body(kind: str, c: dict) -> str:
    """A step as words: a lead its target, the evidence its summary and each quote with its source."""
    if kind == "lead":
        return f"**#{c.get('lead')} · {c.get('agent')}** — {c.get('what')}" + (f" *({c['why']})*" if c.get("why") else "")
    if kind == "evidence":
        head = f"**#{c.get('lead')} · {c.get('agent')} · {c.get('status')}{' · già trovata' if c.get('reused') else ''}** — {c.get('what')}"
        lines = [f"- «{e['quote']}» — *{e['cite']}*" + (f" — {e['note']}" if e.get("note") else "") for e in c.get("evidence", [])]
        return "\n\n".join([head, c.get("summary", ""), "\n".join(lines)]).strip()
    if kind == "search":
        return f"«{c.get('q')}» — {c.get('total', c.get('hits'))} passaggi" + (f" (cercato con: {c['used']})" if c.get("used") and c.get("used") != c.get("q") else "")
    return c.get("text") or json.dumps(c, ensure_ascii=False)
