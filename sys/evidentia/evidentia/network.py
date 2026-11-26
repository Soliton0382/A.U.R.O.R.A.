# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The network of who wrote to whom (owner, 10 Nov: «i movimenti laterali in una rete network»; R20, I8). Built once
from the e-mail headers in the pages (From / To / Cc / Sent or Date / Subject), each message a row with its document
and page; every tie is of a stated kind — «wrote_to» (the sender to a recipient), «copied» (the sender to someone in
copy) — never a «strength» from names that appear together (CLAUDE.md). A lateral move is one tie, with its messages.

Who is shown by name: the project's rules protect victims and private persons, and no list of victims exists yet
(F5). So a correspondent is named only when the archive shows them widely — at least PUBLIC_PEERS distinct
correspondents and PUBLIC_DOCS documents — or when the question names them; anyone else is «a private person» with a
stable label, and the network never walks through them. A name the owner put on the protected list
(network_protected) is never shown, never walked, never answered about. This is a guard, not a victim detector: F5's
protected list remains the real one."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import re
import time
from collections import defaultdict, deque

PUBLIC_PEERS, PUBLIC_DOCS = 3, 5
FAMOUS_DOCS = 20          # or named in at least this many documents of the archive (George Soros: 2 correspondents, 538 documents)
COURTESY = {"mr", "mrs", "ms", "miss", "mx"}
# words that are never part of a person's name: what a header read badly gives as a «name» («For The Past Year», «As
# President», «President» followed by a release's stamp — found trying, 10 Nov; the configured collections' names
# count too: docids); such a «person» is never public, never proposed
NOT_NAME = set("""for the past year years month months day days week as at by of and or to in on with from re fw fwd
pls please thanks thank regards best dear hi hello all team office page pages sent subject date cc bcc ogr bates
attached attachment message original forwarded reply note notes call meeting update info information yes no not new
this that these those your our my his her its their will would can could may might must shall should is are was were
be been am pm today tomorrow yesterday mon tue wed thu fri sat sun""".split())             # «Ms Carla Neri» is Carla Neri; «Dr», «President» stay
def _collection_words() -> set[str]:
    """The configured collections' names (docids): a release's stamp is never part of a person's name."""
    from . import docids
    return {c[0].lower() for c in docids._collections()}


LABELS = ("From", "Sent", "Date", "To", "Cc", "CC", "Bcc", "Subject")
HEADER = re.compile(r"\b(From|Sent|Date|To|Cc|CC|Bcc|Subject)\s*:", re.I)
MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, doc TEXT NOT NULL, page INTEGER NOT NULL, idx INTEGER NOT NULL,
  sender TEXT, day TEXT, subject TEXT);
CREATE INDEX IF NOT EXISTS messages_doc ON messages(doc, page);
CREATE TABLE IF NOT EXISTS ties (msg INTEGER NOT NULL, a TEXT NOT NULL, b TEXT NOT NULL, kind TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ties_a ON ties(a);
CREATE INDEX IF NOT EXISTS ties_b ON ties(b);
CREATE TABLE IF NOT EXISTS people (key TEXT PRIMARY KEY, name TEXT NOT NULL, peers INTEGER, docs INTEGER,
  public INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS network_protected (key TEXT PRIMARY KEY, why TEXT, added REAL);
CREATE TABLE IF NOT EXISTS doc_kinds (doc TEXT PRIMARY KEY, kind TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS network_secret (k BLOB NOT NULL);   -- the private persons' labels: an HMAC key (B25)
"""


def _schema(findings) -> None:
    """The tables, and once the secret the private persons' labels are made with (never leaves findings.db)."""
    findings.executescript(SCHEMA)
    if findings.execute("SELECT 1 FROM network_secret").fetchone() is None:
        findings.execute("INSERT INTO network_secret(k) VALUES (?)", (secrets.token_bytes(32),))


_LOOSE = secrets.token_bytes(32)    # a network built before the secret: labels stable for this process only


def _secret(findings) -> bytes:
    try:
        r = findings.execute("SELECT k FROM network_secret").fetchone()
    except Exception:  # noqa: BLE001 — the table not there yet (an older build)
        r = None
    return bytes(r[0]) if r else _LOOSE


# ---- reading the headers ---------------------------------------------------------------------------------------
def key(name: str) -> str:
    """A person's key: «Rossi, Mario E.» and «Mario E. Rossi» and «mario rossi» are one."""
    n = re.sub(r"<.*?(>|$)|\[.*?(\]|$)|\(.*?(\)|$)|\S+@\S+|[\"'«»>]|mailto", " ", str(name))
    n = re.sub(r"[^A-Za-zÀ-ÿ,.\- ]", " ", n).strip(" ,.-")
    if n.count(",") == 1:
        last, first = (x.strip() for x in n.split(","))
        n = f"{first} {last}"
    words = [w for w in re.split(r"[\s.]+", n.lower()) if len(w) > 1]
    while words and words[0] in COURTESY:
        words = words[1:]
    words = [w for i, w in enumerate(words) if i == 0 or w != words[i - 1]]     # «Luca Luca Bianchi»: OCR twice
    return " ".join(words) if 2 <= len(words) <= 4 and 4 <= len(" ".join(words)) <= 40 else ""


def _display(name: str) -> str:
    return name if name.startswith("@") else " ".join("-".join(p.capitalize() for p in w.split("-")) for w in key(name).split())


ADDRESS = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
ALIAS = re.compile(r"([A-Z][A-Za-z.'\- ]{2,40}?)\s*(?:<|\[mailto:)\s*([\w.+-]+@[\w-]+(?:\.[\w-]+)+)")


def _who(part: str) -> str:
    """A name's key, or «@address» when the field holds only an address (named later by its aliases)."""
    k = key(part)
    if k:
        return k
    m = ADDRESS.search(part)
    return "@" + m.group(0).lower().rstrip(".") if m else ""


def _people(value: str) -> list[str]:
    """The names in a To or Cc field: split on «;», or on «,» when it is not a «Last, First»."""
    parts = value.split(";") if ";" in value else (
        [value] if value.count(",") == 1 and len(value.split()) <= 4 else value.split(","))
    return [k for k in (_who(p) for p in parts) if k]


def aliases(text: str) -> list[tuple[str, str]]:
    """(address, name key) pairs a page shows: «Mario Rossi <mrossi@example.com>»."""
    return [(a.lower(), k) for n, a in ALIAS.findall(text or "") if (k := key(n))]


def _day(value: str) -> str:
    v = value.lower()
    m = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2}),?\s+((?:19|20)\d\d)", v)
    if m:
        return f"{m.group(3)}-{MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}"
    m = re.search(r"\b(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+((?:19|20)\d\d)", v)
    if m:
        return f"{m.group(3)}-{MONTHS[m.group(2)]:02d}-{int(m.group(1)):02d}"
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/((?:19|20)\d\d)", v)
    if m and int(m.group(1)) <= 12:
        return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return ""


def messages(text: str) -> list[dict]:
    """Every header block of a page: {sender, to, cc, day, subject}; a block without a sender's name (redacted, or
    read badly) gives no tie."""
    out, cur = [], None
    marks = list(HEADER.finditer(text or ""))
    for i, m in enumerate(marks):
        label = m.group(1).capitalize()
        value = text[m.end():marks[i + 1].start() if i + 1 < len(marks) else min(len(text), m.end() + 300)][:300]
        if label == "From":
            if cur:
                out.append(cur)
            cur = {"sender": _who(value.split(" Sent")[0].split(" Date")[0][:120]), "to": [], "cc": [], "day": "",
                   "subject": ""}
        elif cur is None:
            continue
        elif label in ("To",):
            cur["to"] += _people(value)
        elif label in ("Cc", "Bcc"):
            cur["cc"] += _people(value)
        elif label in ("Sent", "Date") and not cur["day"]:
            cur["day"] = _day(value)
        elif label == "Subject" and not cur["subject"]:
            cur["subject"] = " ".join(value.split())[:160]
    if cur:
        out.append(cur)
    return [x for x in out if x["sender"] and (x["to"] or x["cc"])]


def kind_of(text: str) -> str:
    t = text[:6000]
    if HEADER.search(t) and re.search(r"\b(To|Sent|Subject)\s*:", t):
        return "email"
    if re.search(r"UNITED STATES DISTRICT COURT|Case No\.?|IN THE CIRCUIT COURT|Plaintiffs?\b.*\bDefendants?\b", t, re.S):
        return "court"
    if re.search(r"\bDEPOSITION\b|\bVIDEOTAPED\b|^\s*Q\.\s", t, re.M) or len(re.findall(r"\b[QA]\.\s", t)) >= 6:
        return "testimony"
    if re.search(r"Bulletin|bulletinintelligence|Reuters|Bloomberg|Associated Press|New York Times|Washington Post|"
                 r"Wall Street Journal|Daily Mail|Fox News|\(AP\)", t):
        return "news"
    if re.search(r"Account (Number|Summary)|Beginning Balance|Statement Period|Wire Transfer|ABA|SWIFT", t):
        return "financial"
    return "other"


# ---- building it ------------------------------------------------------------------------------------------------
def build(corpus, findings, say=print, every: int = 200_000) -> dict:
    """The whole network again (idempotent: the tables made anew), from the pages of the corpus."""
    _schema(findings)
    for t in ("messages", "ties", "people", "doc_kinds"):
        findings.execute(f"DELETE FROM {t}")
    t0, n_pages, n_msg = time.time(), 0, 0
    kinds: dict[str, str] = {}
    named: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    cur = findings.cursor()
    for doc, page, text in corpus.execute("SELECT doc, page, text FROM pages ORDER BY doc, page"):
        n_pages += 1
        if kinds.get(doc, "other") == "other":            # the first page that says what the document is
            kinds[doc] = kind_of(text or "")
        for addr, k in aliases(text or ""):
            named[addr][k] += 1
        for i, m in enumerate(messages(text or "")):
            cur.execute("INSERT INTO messages(doc, page, idx, sender, day, subject) VALUES (?,?,?,?,?,?)",
                        (doc, page, i, m["sender"], m["day"], m["subject"]))
            mid = cur.lastrowid
            n_msg += 1
            for r in set(m["to"]) - {m["sender"]}:
                cur.execute("INSERT INTO ties(msg, a, b, kind) VALUES (?,?,?,'wrote_to')", (mid, m["sender"], r))
            for r in set(m["cc"]) - {m["sender"]} - set(m["to"]):
                cur.execute("INSERT INTO ties(msg, a, b, kind) VALUES (?,?,?,'copied')", (mid, m["sender"], r))
        if n_pages % every == 0:
            findings.commit()
            say(f"network: {n_pages:,} pages, {n_msg:,} messages, {time.time() - t0:.0f} s")
    findings.executemany("INSERT INTO doc_kinds(doc, kind) VALUES (?,?)", kinds.items())
    # an address alone is the person the archive most often writes beside it (at least twice); else it stays an address
    for addr, names in named.items():
        k, n = max(names.items(), key=lambda x: x[1])
        if n >= 2:
            for col in ("a", "b"):
                findings.execute(f"UPDATE ties SET {col} = ? WHERE {col} = ?", (k, "@" + addr))
            findings.execute("UPDATE messages SET sender = ? WHERE sender = ?", (k, "@" + addr))
    people_table(corpus, findings)
    out = {"pages": n_pages, "messages": n_msg, "ties": findings.execute("SELECT COUNT(*) FROM ties").fetchone()[0],
           "people": findings.execute("SELECT COUNT(*) FROM people").fetchone()[0],
           "public": findings.execute("SELECT COUNT(*) FROM people WHERE public = 1").fetchone()[0],
           "seconds": round(time.time() - t0)}
    say(f"network: done {out}")
    return out


# ---- asking it ----------------------------------------------------------------------------------------------------
def people_table(corpus, findings) -> int:
    """The people of the network made anew from its ties (a derived table: dropped and made again, so a column added
    later is never missing — 10 Nov, «no such column: public» after an older build), then who may be named."""
    findings.execute("DROP TABLE IF EXISTS people")
    _schema(findings)
    findings.execute("""INSERT INTO people(key, name, peers, docs)
        SELECT k, k, COUNT(DISTINCT other), COUNT(DISTINCT doc) FROM (
          SELECT t.a AS k, t.b AS other, m.doc AS doc FROM ties t JOIN messages m ON m.id = t.msg
          UNION ALL SELECT t.b, t.a, m.doc FROM ties t JOIN messages m ON m.id = t.msg) GROUP BY k""")
    for k, in list(findings.execute("SELECT key FROM people")):
        findings.execute("UPDATE people SET name = ? WHERE key = ?", (_display(k), k))
    # who may be named: shown widely by the e-mails, or named in many documents of the archive (I11); never a «name»
    # made of words that are not names
    findings.execute("UPDATE people SET public = 1 WHERE peers >= ? AND docs >= ?", (PUBLIC_PEERS, PUBLIC_DOCS))
    for k, in list(findings.execute("SELECT key FROM people WHERE public = 1")):
        if set(k.split()) & (NOT_NAME | _collection_words()):
            findings.execute("UPDATE people SET public = 0 WHERE key = ?", (k,))
    for k, in list(findings.execute("SELECT key FROM people WHERE public = 0 AND docs >= 1 AND key NOT LIKE '@%'")):
        if set(k.split()) & (NOT_NAME | _collection_words()):
            continue
        n = corpus.execute("SELECT COUNT(*) FROM (SELECT DISTINCT p.doc FROM passages_fts f JOIN passages p ON p.id = f.rowid "
                           "WHERE passages_fts MATCH ? LIMIT ?)", ('"' + k.replace('"', "") + '"', FAMOUS_DOCS)).fetchone()[0]
        if n >= FAMOUS_DOCS:
            findings.execute("UPDATE people SET public = 1 WHERE key = ?", (k,))
    findings.commit()
    return findings.execute("SELECT COUNT(*) FROM people WHERE public = 1").fetchone()[0]


def _protected(findings) -> set[str]:
    try:
        return {r[0] for r in findings.execute("SELECT key FROM network_protected")}
    except Exception:  # noqa: BLE001 — a network not built yet: nothing protected to read
        return set()


def _shown(findings, k: str, asked: set[str]) -> dict:
    """A person as an answer shows them: by name when public or asked, else a stable private label."""
    r = None if k in _protected(findings) else \
        findings.execute("SELECT name, peers, docs, public FROM people WHERE key = ?", (k,)).fetchone()
    public = bool(r) and bool(r[3])                     # a protected name reads as a name not in the network (B16)
    if k in asked or public:                           # a private person asked by name: asked, never «public» (B25)
        return {"name": r[0] if r else _display(k), "key": k, "public": public or not r, "asked": k in asked and not public,
                "peers": r[1] if r else 0, "docs": r[2] if r else 0}
    # an HMAC with the archive's secret, not a bare hash: guessing a name no longer confirms its label (B25)
    return {"name": "persona privata " + hmac.new(_secret(findings), k.encode(), hashlib.sha256).hexdigest()[:6],
            "public": False}


class Ambiguous(LookupError):
    """A part of a name that fits several people: the candidates, for the one asking to choose."""
    def __init__(self, candidates: list[dict]):
        super().__init__("several people fit")
        self.candidates = candidates


def people(findings, part: str, limit: int = 20) -> list[dict]:
    """The public people whose name holds every word given — a first name, a surname, a title as the headers write it
    («president», «prince», «dr»): owner, 10 Nov, «non deve limitarsi a nome e cognome». Most documented first."""
    words = [w for w in re.split(r"[\s.,]+", str(part).lower()) if len(w) > 1][:4]
    if not words:
        return []
    prot = _protected(findings)
    where = " AND ".join("(' ' || key || ' ') LIKE ?" for _ in words)
    for pattern in ("% {} %", "% {}%"):                  # the whole word first («dr» is Dr, not Drokova), then its start
        rows = findings.execute(f"SELECT key, name, peers, docs FROM people WHERE {where} AND public = 1 "
                                "ORDER BY docs DESC LIMIT ?",
                                (*[pattern.format(w) for w in words], min(int(limit), 50) + len(prot))).fetchall()
        if rows:
            break
    return [{"name": n, "key": k, "peers": p, "docs": d} for k, n, p, d in rows if k not in prot][:limit]


def _resolve(findings, name: str) -> str:
    """A full name as given; one word, a part, a title: the one public person it fits, or Ambiguous with the choice.
    A protected name is answered exactly as a name nobody in the network has (audit E1, B16: a 403 told which names
    are on the list); the callers find nothing for it, since its ties are never read."""
    k = key(name)
    if k and k not in _protected(findings) and findings.execute("SELECT 1 FROM people WHERE key = ?", (k,)).fetchone():
        return k
    found = people(findings, name, 12)
    if len(found) == 1 or (found and k and found[0]["key"] == k):
        return found[0]["key"]
    if found:
        raise Ambiguous(found)
    if not k:
        raise ValueError("nobody in the network fits these words")
    return k


def contacts(findings, name: str, limit: int = 30) -> dict:
    """The lateral moves from one person: who they wrote to and who wrote to them, each tie with its count, its span
    of days and two of its messages (document, page)."""
    k, prot = _resolve(findings, name), _protected(findings)
    rows = [] if k in prot else findings.execute("""SELECT CASE WHEN t.a = ? THEN t.b ELSE t.a END AS other,
            CASE WHEN t.a = ? THEN t.kind ELSE t.kind || '_by' END AS how, COUNT(*) AS n, MIN(NULLIF(m.day, '')), MAX(NULLIF(m.day, '')),
            GROUP_CONCAT(m.doc || '|' || m.page, ',') FROM ties t JOIN messages m ON m.id = t.msg
            WHERE t.a = ? OR t.b = ? GROUP BY other, how ORDER BY n DESC LIMIT ?""",
                            (k, k, k, k, min(int(limit), 100) * 3)).fetchall()
    out, hidden = [], 0
    for other, how, n, first, last, where in rows:
        if other in prot:
            hidden += 1
            continue
        who = _shown(findings, other, {k})
        out.append({**who, "tie": how, "messages": n, "first": first or "", "last": last or "",
                    "seen_in": sorted(set(where.split(",")))[:2]})
        if len(out) >= limit:
            break
    return {"person": _shown(findings, k, {k}), "contacts": out, "protected_left_out": hidden,
            "rule": "ties from e-mail headers only (wrote_to, copied; «_by» when the other wrote); private persons by label"}


def between(findings, a: str, b: str, limit: int = 50) -> dict:
    """The messages between two people, both ways, in order of day."""
    ka, kb = _resolve(findings, a), _resolve(findings, b)
    rows = [] if {ka, kb} & _protected(findings) else findings.execute("""SELECT m.doc, m.page, m.day, m.subject, t.kind, t.a FROM ties t JOIN messages m ON m.id = t.msg
            WHERE (t.a = ? AND t.b = ?) OR (t.a = ? AND t.b = ?) ORDER BY m.day LIMIT ?""",
                            (ka, kb, kb, ka, min(int(limit), 200))).fetchall()
    return {"a": _shown(findings, ka, {ka}), "b": _shown(findings, kb, {kb}),
            "messages": [{"doc": d, "page": p, "day": day or "", "subject": s or "", "tie": kind,
                          "from": "a" if frm == ka else "b"} for d, p, day, s, kind, frm in rows]}


def path(findings, a: str, b: str, depth: int = 3) -> dict:
    """The shortest chain of documented ties from one person to another, through public people only, at most `depth`
    ties; each tie with one message that shows it."""
    ka, kb = _resolve(findings, a), _resolve(findings, b)
    prot, depth = _protected(findings), max(1, min(int(depth), 4))
    public = {r[0] for r in findings.execute("SELECT key FROM people WHERE public = 1")}
    prev, seen, q = {}, {ka}, deque([] if ka in prot else [(ka, 0)])
    while q:
        node, d = q.popleft()
        if node == kb or d == depth:
            continue
        for (other,) in findings.execute("SELECT b FROM ties WHERE a = ? UNION SELECT a FROM ties WHERE b = ?", (node, node)):
            if other in seen or other in prot or (other != kb and other not in public):
                continue
            seen.add(other)
            prev[other] = node
            q.append((other, d + 1))
    if kb not in prev:
        return {"a": _shown(findings, ka, {ka}), "b": _shown(findings, kb, {kb}), "chain": [],
                "said": f"no chain of at most {depth} documented ties through public people"}
    chain, cur = [], kb
    while cur != ka:
        p = prev[cur]
        m = findings.execute("""SELECT m.doc, m.page, m.day, t.kind, t.a FROM ties t JOIN messages m ON m.id = t.msg
            WHERE (t.a = ? AND t.b = ?) OR (t.a = ? AND t.b = ?) ORDER BY m.day LIMIT 1""", (p, cur, cur, p)).fetchone()
        chain.append({"from": _shown(findings, p, {ka, kb})["name"], "to": _shown(findings, cur, {ka, kb})["name"],
                      "tie": m[3], "doc": m[0], "page": m[1], "day": m[2] or ""})
        cur = p
    return {"a": _shown(findings, ka, {ka}), "b": _shown(findings, kb, {kb}), "chain": list(reversed(chain))}


def protect(findings, name: str, why: str = "") -> str:
    k = key(name)
    if not k:
        raise ValueError("a person's name of two to four words")
    _schema(findings)
    findings.execute("INSERT OR REPLACE INTO network_protected(key, why, added) VALUES (?,?,?)", (k, why[:200], time.time()))
    findings.commit()
    return k


def stats(findings) -> dict:
    try:
        q = lambda s: findings.execute(s).fetchone()[0]   # noqa: E731
        return {"messages": q("SELECT COUNT(*) FROM messages"), "ties": q("SELECT COUNT(*) FROM ties"),
                "people": q("SELECT COUNT(*) FROM people"),   # how many are protected is not said (B16)
                "kinds": dict(findings.execute("SELECT kind, COUNT(*) FROM doc_kinds GROUP BY kind").fetchall())}
    except Exception:  # noqa: BLE001
        return {"built": False}
