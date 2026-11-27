# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""💰 Follow the money (owner, 27 Nov: «voglio una cosa automatica che caccia, trova e correla… dobbiamo capire la rete
che ci sta dietro, di solito si dice: seguire i soldi, facciamolo»).

From what the inventory already found on every page (identifiers: account numbers, ABA routing numbers, BIC, IBAN,
amounts) the pages where money moves are read again and correlated:
  - each page's accounts, amounts, dates, banks, and the parties its fields name (ACCOUNT NAME, BENEFICIARY, FOR
    CREDIT TO, ORDERING CUSTOMER, PAY TO, REMITTER, ORIGINATOR…);
  - what appears together on the same pages becomes a tie (account–party, account–bank, party–party), each with the
    pages it rests on;
  - kept in the archive's own money.db (entities, mentions, relations: findings' schema), read only from the rest —
    the inventory and the OCR write findings.db the whole time, a second writer never got its turn (27 Nov).
The rules hold here as everywhere in Evidentia: a protected name (a victim, a redacted one) is never kept nor shown;
a person who is not public in the archive's network is kept as «private person #…», never by name; an account's
number is kept whole (to correlate) and shown only by its last four digits. Everything said comes with its pages."""
from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter, defaultdict

KINDS = ("account", "aba", "bic", "iban")
LABELS = re.compile(
    r"\b(ACCOUNT NAME|ACCT NAME|BENEFICIARY(?: NAME| CUSTOMER)?|FOR (?:FURTHER )?CREDIT (?:TO|OF)|ORDERING (?:CUSTOMER|PARTY|INSTITUTION)|"
    r"PAY TO(?: THE ORDER OF)?|REMITTER|ORIGINATOR(?: NAME)?|SENDER|RECEIVER|ACCOUNT HOLDER|IN FAVOU?R OF|ATTN)\b\s*[:#\-]?\s*", re.I)
STOP = re.compile(r"^(ACCOUNT|ACCT|ABA|SWIFT|BIC|IBAN|ADDRESS|BANK|ROUTING|AMOUNT|DATE|REF|REFERENCE|NO|NUMBER|TEL|PHONE|FAX|"
                  r"BENEFICIARY|ORDERING|DETAILS|INTERMEDIARY|CURRENCY|VALUE|USD|EUR|CHF|GBP)$", re.I)
ORG = re.compile(r"\b(LLC|L\.L\.C|INC|LTD|LIMITED|LP|L\.P|LLP|TRUST|FOUNDATION|CORP|CORPORATION|COMPANY|CO|BANK|FUND|CAPITAL|"
                 r"HOLDINGS|GROUP|PARTNERS|ASSOCIATES|ESTATE|ENTERPRISES|MANAGEMENT|INVESTMENTS?|SECURITIES|S\.A|AG|GMBH|"
                 r"N\.A|PLC|FINANCIAL|ADVISORS|SERVICES|UNIVERSITY|INSTITUTE|SOCIETY)\b\.?", re.I)
BANK = re.compile(r"\b((?:[A-Z][\w&.'-]*\s){0,3}(?:Bank|BANK|Bancorp|BANCORP|Banque|BANQUE)(?:\s(?:of|OF)\s(?:[A-Z][\w&.'-]*\s?){1,3})?"
                  r"|JPMorgan(?:\sChase)?|J\.P\. Morgan|Morgan Stanley|Goldman Sachs|Citibank|Citigroup|UBS|HSBC|Barclays|"
                  r"Credit Suisse|Wells Fargo|Bank of America|Deutsche Bank)\b")
DATE = re.compile(r"\b(?:(19[89]\d|20[0-2]\d)[-/.](0?[1-9]|1[0-2])[-/.](0?[1-9]|[12]\d|3[01])|(0?[1-9]|1[0-2])/(0?[1-9]|[12]\d|3[01])/"
                  r"(19[89]\d|20[0-2]\d|\d\d))\b")


def amount(value: str) -> tuple[str, float] | None:
    """«USD 1,234.56» → ("USD", 1234.56); the separators read as written (a last group of two is the cents)."""
    m = re.match(r"([A-Z]{3})\s+([\d.,]+)$", value.strip())
    if not m:
        return None
    cur, n = m.group(1), m.group(2)
    if re.search(r"[.,]\d{2}$", n):
        whole, cents = n[:-3], n[-2:]
    else:
        whole, cents = n, "0"
    try:
        return cur, float(re.sub(r"[.,]", "", whole) or 0) + int(cents) / 100
    except ValueError:
        return None


def mask_account(v: str) -> str:
    return "…" + v[-4:] if len(v) > 4 else "…" + v


def _party(text: str) -> str | None:
    """The name a field gives: up to six words, stopped by digits, another field, or the end."""
    words = []
    for w in text.split()[:9]:
        w = w.strip(",;")
        if not w or any(ch.isdigit() for ch in w) or STOP.match(w.strip(".:")) or w.endswith(":"):
            break
        if not re.match(r"^[A-Za-zÀ-ÿ&.'\-/]+$", w):
            break
        words.append(w)
        if len(words) == 6:
            break
    name = " ".join(words).strip(" .-/&")
    return name if len(name) >= 3 and len(words) >= 1 and not STOP.match(name) else None


def read_page(text: str) -> dict:
    """What a money page says, beside its identifiers (found by the inventory): parties, banks, dates."""
    parties = set()
    for m in LABELS.finditer(text):
        p = _party(text[m.end():m.end() + 120])
        if p:
            parties.add(p)
    banks = {re.sub(r"\s+", " ", b.group(1)).strip() for b in BANK.finditer(text)}
    days = set()
    for d in DATE.finditer(text):
        if d.group(1):
            days.add(f"{d.group(1)}-{int(d.group(2)):02d}-{int(d.group(3)):02d}")
        else:
            y = d.group(6)
            y = int(y) + (1900 if len(y) == 2 and int(y) > 50 else 2000 if len(y) == 2 else 0)
            days.add(f"{y:04d}-{int(d.group(4)):02d}-{int(d.group(5)):02d}")
    return {"parties": sorted(parties), "banks": sorted(banks), "days": sorted(days)}


def split_party(name: str) -> list[str]:
    """A field often holds a signer and a company («LAUREN SAMPLE NYSG LLC»): with three words or more before the
    legal form, the first two are the signer and the rest the company; with fewer, all of it is the company."""
    toks = [t for t in name.split()]
    while toks and toks[0].upper().strip(":") in ("RECIPIENT", "NAME", "ACCOUNT", "THE", "MR", "MRS", "MS", "DR"):
        toks = toks[1:]
    for i, t in enumerate(toks):
        legal = ORG.fullmatch(t.strip(".,")) or (t == "&" and i + 1 < len(toks) and ORG.fullmatch(toks[i + 1].strip(".,")))
        if not legal:
            continue
        end = i + 1
        while end < len(toks) and (ORG.fullmatch(toks[end].strip(".,")) or toks[end] == "&"):
            end += 1
        if i >= 3:
            return [" ".join(toks[:2]), " ".join(toks[2:end])]
        return [" ".join(toks[:end])]
    return [" ".join(toks)] if toks else []


def bank_name(raw: str) -> str | None:
    """A bank's name as one: the words before BANK (at most three, none with a digit nor a stray first word), upper
    case; «Bank» alone or OCR noise left out."""
    raw = re.split(r"[.;:,]", raw)[-1].strip()
    toks = raw.upper().split()
    if not toks:
        return None
    if "BANK" in toks:
        i = toks.index("BANK")
        before = [t for t in toks[max(0, i - 3):i] if t.isalpha() and t not in ("IMAGE", "THE", "L", "M", "J", "AT", "FROM", "TO")]
        after = toks[i + 1:i + 4] if i + 1 < len(toks) and toks[i + 1] == "OF" else []
        before = [t for t in before if t not in GENERIC]
        name = " ".join(before + ["BANK"] + [t for t in after if t.isalpha()])
        return _family(name) if before or after else None
    name = " ".join(t for t in toks if t.isalpha())
    return _family(name) if name and name not in ("MORGAN",) else None


GENERIC = {"RECEIVING", "INTERMEDIARY", "CORRESPONDENT", "BENEFICIARY", "ORDERING", "SENDING", "ORIGINATING", "PAYING",
           "BENEFICIARYS", "YOUR", "OUR", "A", "PRIVATE", "NEW", "FIRST"}
FAMILIES = (("JPMORGAN", "JPMORGAN CHASE"), ("J P MORGAN", "JPMORGAN CHASE"), ("CHASE", "JPMORGAN CHASE"),
            ("DEUTSCHE", "DEUTSCHE BANK"), ("CITI", "CITIBANK"), ("WELLS FARGO", "WELLS FARGO"), ("UBS", "UBS"),
            ("BANK OF AMERICA", "BANK OF AMERICA"), ("MORGAN STANLEY", "MORGAN STANLEY"), ("HSBC", "HSBC"),
            ("BARCLAYS", "BARCLAYS"), ("CREDIT SUISSE", "CREDIT SUISSE"), ("GOLDMAN", "GOLDMAN SACHS"),
            ("FIFTH THIRD", "FIFTH THIRD BANK"), ("WACHOVIA", "WACHOVIA BANK"), ("COLONIAL", "COLONIAL BANK"),
            ("TORONTO DOMINION", "TD BANK"), ("FIRST BANK", "FIRSTBANK"))


def _family(name: str) -> str:
    """One name for a bank's family (JPMORGAN, JPMORGAN CHASE BANK, JPMORGAN PRIVATE BANK → JPMORGAN CHASE)."""
    flat = name.replace(".", " ").replace("  ", " ")
    for start, fam in FAMILIES:
        if flat.startswith(start) or f" {start}" in f" {flat}":
            return fam
    return name


LEGAL = ((r"\bCORPORATIO\w*|\bCORPORATION\b|\bCORP\b\.?", "CORP"), (r"\bINCORPORATED\b|\bINC\b\.?", "INC"),
         (r"\bLIMITED\b|\bLTD\b\.?", "LTD"), (r"\bL\.?L\.?C\b\.?", "LLC"), (r"\bCOMPANY\b|\bCO\b\.?", "CO"),
         (r"\s+A\s+(?=CO\b)", " & "))


def org_key(name: str) -> str:
    """A company's name with its legal form written one way («ZORRO DEVELOPMENT CORPORATIO» → «ZORRO DEVELOPMENT CORP»)."""
    k = name.upper()
    for rx, to in LEGAL:
        k = re.sub(rx, to, k)
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9& ]+", " ", k)).strip()


def _one_apart(a: str, b: str) -> bool:
    """Equal but for one letter changed, added or lost (the OCR's NYSG, NYSO, NVSG)."""
    if a == b or abs(len(a) - len(b)) > 1 or min(len(a), len(b)) < 4:
        return a == b
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    s, t = (a, b) if len(a) < len(b) else (b, a)
    return any(t[:i] + t[i + 1:] == s for i in range(len(t)))


def merge_orgs(counts: dict[str, int]) -> dict[str, str]:
    """name → the name it is one with: the same legal form, the rest one letter apart; the most seen name kept."""
    by_form: dict[tuple, list[str]] = defaultdict(list)
    keyed = {n: org_key(n) for n in counts}
    for n, k in keyed.items():
        toks = k.split()
        by_form[(toks[-1] if toks else "", len(toks))].append(n)
    out = {}
    for names in by_form.values():
        names.sort(key=lambda n: -counts[n])
        heads: list[str] = []
        for n in names:
            core = " ".join(keyed[n].split()[:-1])
            for h in heads:
                if keyed[h] == keyed[n] or _one_apart(" ".join(keyed[h].split()[:-1]), core):
                    out[n] = h
                    break
            else:
                heads.append(n)
                out[n] = n
    return out


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def shown(name: str, public: set[str], protected: tuple[str, ...]) -> tuple[str, str, int]:
    """(the name kept, its kind, protected?): a company or a bank by its name; a person by name only if public in
    the network, else «private person #…»; a protected one never."""
    k = _key(name)
    if any(_key(p) and _key(p) in k for p in protected):
        return "", "person", 1
    if ORG.search(name) or BANK.fullmatch(name):
        return name, "org", 0
    if k in public:
        return name, "person", 0
    return "private person #" + hashlib.sha256(k.encode()).hexdigest()[:6], "person", 0


SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (id INTEGER PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL,
  protected INTEGER NOT NULL DEFAULT 0, UNIQUE (name, kind));
CREATE TABLE IF NOT EXISTS mentions (entity INTEGER, doc TEXT, page INTEGER, start INTEGER, end INTEGER, role TEXT);
CREATE INDEX IF NOT EXISTS mentions_entity ON mentions(entity);
CREATE TABLE IF NOT EXISTS relations (id INTEGER PRIMARY KEY, a INTEGER, b INTEGER, kind TEXT, strength INTEGER,
  evidence TEXT, verified_by TEXT, found_in_case TEXT, created REAL);
CREATE INDEX IF NOT EXISTS relations_a ON relations(a);
CREATE INDEX IF NOT EXISTS relations_b ON relations(b);
"""


def open_db(data_dir):
    import sqlite3
    con = sqlite3.connect(str(data_dir / "money.db"), timeout=60)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    return con


def run(corpus, findings, protected: tuple[str, ...] = (), say=print, limit: int | None = None, out=None) -> dict:
    """Read the money pages (corpus and findings, read only), correlate, keep the ties in `out` (money.db)."""
    t0 = time.time()
    try:                                             # the network's people (made by evd_network): who is public
        public = {_key(r[0]) for r in findings.execute("SELECT name FROM people WHERE public = 1") if r[0]}
    except Exception:  # noqa: BLE001 — an archive whose network was never built: nobody is public
        public = set()
    pages = defaultdict(lambda: {"ids": set(), "amounts": []})
    for kind, value, doc, page in findings.execute(
            "SELECT kind, value, doc, page FROM identifiers WHERE valid = 1 AND kind IN ('account','aba','bic','iban','amount')"):
        if kind == "amount":
            continue
        pages[(doc, page)]["ids"].add((kind, value.replace(" ", "").upper()))
    keys = sorted(pages)[:limit] if limit else sorted(pages)
    for (doc, page) in keys:                         # the amounts of those pages only
        for (value,) in findings.execute("SELECT value FROM identifiers WHERE kind='amount' AND doc=? AND page=?", (doc, page)):
            a = amount(value)
            if a:
                pages[(doc, page)]["amounts"].append(a)
    say(f"{len(keys)} money pages in {len({d for d, _ in keys})} documents")
    nodes: dict[tuple[str, str], dict] = {}
    ties: dict[tuple, dict] = {}

    def node(kind: str, name: str, prot: int = 0):
        k = (kind, name)
        if k not in nodes:
            nodes[k] = {"pages": set(), "amounts": Counter(), "days": set(), "protected": prot}
        return nodes[k]

    for i, (doc, page) in enumerate(keys, 1):
        row = corpus.execute("SELECT text FROM pages WHERE doc = ? AND page = ?", (doc, page)).fetchone()
        info = read_page(row[0] if row else "")
        here = set()
        for kind, v in pages[(doc, page)]["ids"]:
            here.add(("account" if kind in ("account", "iban") else "bank_code", f"{kind}:{v}"))
        for b in info["banks"]:
            name = bank_name(b)
            if name:
                here.add(("bank", name))
        for whole in info["parties"]:
            for p in split_party(whole):
                if BANK.search(p):                   # a bank named in a party's field: a bank
                    name = bank_name(p)
                    if name:
                        here.add(("bank", name))
                    continue
                name, kind, prot = shown(p.upper(), public, protected)        # one case: «Jeffrey»/«JEFFREY»
                if prot:
                    continue
                here.add(("org" if kind == "org" else "person", name))
        for k in here:
            n = node(*k)
            n["pages"].add((doc, page))
            for cur, val in pages[(doc, page)]["amounts"]:
                n["amounts"][cur] += val
            n["days"].update(info["days"])
        items = sorted(here)
        for a in range(len(items)):
            for b in range(a + 1, len(items)):
                t = ties.setdefault((items[a], items[b]), {"pages": set()})
                t["pages"].add((doc, page))
        if i % 5000 == 0:
            say(f"  {i}/{len(keys)} pages read, {len(nodes)} names and accounts, {len(ties)} ties")
    nodes, ties = _merged(nodes, ties)
    _keep(out if out is not None else findings, nodes, ties)
    return {"pages": len(keys), "nodes": len(nodes), "ties": len(ties), "seconds": round(time.time() - t0, 1)}


def _merged(nodes: dict, ties: dict) -> tuple[dict, dict]:
    """The companies written several ways by the OCR made one (merge_orgs), their pages and ties joined."""
    alias = merge_orgs({name: len(n["pages"]) for (kind, name), n in nodes.items() if kind == "org"})
    to = lambda k: ("org", alias.get(k[1], k[1])) if k[0] == "org" else k   # noqa: E731
    new_nodes: dict = {}
    for k, n in nodes.items():
        m = new_nodes.setdefault(to(k), {"pages": set(), "amounts": Counter(), "days": set(), "protected": n["protected"]})
        m["pages"] |= n["pages"]
        m["amounts"].update(n["amounts"])
        m["days"] |= n["days"]
    new_ties: dict = {}
    for (a, b), t in ties.items():
        a2, b2 = to(a), to(b)
        if a2 == b2:
            continue
        key = tuple(sorted((a2, b2)))
        new_ties.setdefault(key, {"pages": set()})["pages"] |= t["pages"]
    return new_nodes, new_ties


def _keep(findings, nodes: dict, ties: dict) -> None:
    """The money's entities and ties written again whole (kind money_*: the inventory's own rows untouched). The long
    read is closed first and the writing asked for at once (BEGIN IMMEDIATE waits its turn): a read turned into a write
    while the OCR wrote meanwhile is refused at once by SQLite, whatever the busy timeout (measured 27 Nov)."""
    findings.commit()
    findings.execute("BEGIN IMMEDIATE")
    findings.execute("DELETE FROM relations WHERE kind LIKE 'money_%'")
    findings.execute("DELETE FROM mentions WHERE role = 'money'")
    ids = {}
    for (kind, name), n in nodes.items():
        findings.execute("INSERT OR IGNORE INTO entities(name, kind, protected) VALUES (?,?,?)", (name, f"money_{kind}", n["protected"]))
        ids[(kind, name)] = findings.execute("SELECT id FROM entities WHERE name=? AND kind=?", (name, f"money_{kind}")).fetchone()[0]
        findings.executemany("INSERT INTO mentions(entity, doc, page, start, end, role) VALUES (?,?,?,0,0,'money')",
                             [(ids[(kind, name)], d, p) for d, p in sorted(n["pages"])])
    now = time.time()
    findings.executemany("INSERT INTO relations(a, b, kind, strength, evidence, verified_by, found_in_case, created) "
                         "VALUES (?,?,?,?,?,NULL,NULL,?)",
                         [(ids[a], ids[b], f"money_{a[0]}_{b[0]}", len(t["pages"]),
                           json.dumps(sorted(t["pages"])[:50]), now) for (a, b), t in ties.items()])
    findings.commit()


def report(findings, top: int = 15) -> dict:
    """The strongest of what was found: accounts seen on the most pages, the organisations and banks around them, the
    names that tie the most accounts together — each with pages to read."""
    def ents(kind):
        return findings.execute(
            "SELECT e.id, e.name, COUNT(m.doc) n FROM entities e JOIN mentions m ON m.entity = e.id AND m.role = 'money' "
            "WHERE e.kind = ? AND e.protected = 0 GROUP BY e.id ORDER BY n DESC LIMIT ?", (f"money_{kind}", top)).fetchall()

    def pages_of(eid, k=3):
        return [list(r) for r in findings.execute("SELECT doc, page FROM mentions WHERE entity=? AND role='money' LIMIT ?", (eid, k))]

    def hubs():
        return findings.execute(
            "SELECT e.id, e.name, e.kind, COUNT(DISTINCT CASE WHEN r.a = e.id THEN r.b ELSE r.a END) links FROM entities e "
            "JOIN relations r ON (r.a = e.id OR r.b = e.id) AND r.kind LIKE 'money_%' "
            "JOIN entities o ON o.id = CASE WHEN r.a = e.id THEN r.b ELSE r.a END AND o.kind = 'money_account' "
            "WHERE e.kind IN ('money_org','money_person') AND e.protected = 0 "
            "GROUP BY e.id ORDER BY links DESC LIMIT ?", (top,)).fetchall()

    def shared(kinds=("money_org", "money_person")):
        """Organisations and people that appear with the same accounts: who moves money through the same place."""
        ks = ",".join(f"'{k}'" for k in kinds)
        rows = findings.execute(
            "WITH ea AS (SELECT CASE WHEN ea.kind='money_account' THEN r.b ELSE r.a END p, "
            "CASE WHEN ea.kind='money_account' THEN r.a ELSE r.b END acc FROM relations r JOIN entities ea ON ea.id = r.a "
            "JOIN entities eb ON eb.id = r.b WHERE r.kind LIKE 'money_%' AND "
            f"((ea.kind='money_account' AND eb.kind IN ({ks})) OR (eb.kind='money_account' AND ea.kind IN ({ks})))) "
            "SELECT x.p, y.p, COUNT(DISTINCT x.acc) n FROM ea x JOIN ea y ON x.acc = y.acc AND x.p < y.p "
            "GROUP BY x.p, y.p ORDER BY n DESC LIMIT ?", (top,)).fetchall()
        name = lambda i: findings.execute("SELECT name, protected FROM entities WHERE id=?", (i,)).fetchone()   # noqa: E731
        out = []
        for a, b, n in rows:
            na, nb = name(a), name(b)
            if na[1] or nb[1]:
                continue
            out.append({"a": na[0], "b": nb[0], "accounts": n, "see": pages_of(a, 2)})
        return out

    out = {"shared": shared(), "org_shared": shared(("money_org",)), "accounts": [{"account": mask_account(n.split(":", 1)[1]), "kind": n.split(":", 1)[0], "pages": c,
                         "see": pages_of(i)} for i, n, c in ents("account")],
           "orgs": [{"name": n, "pages": c, "see": pages_of(i)} for i, n, c in ents("org")],
           "banks": [{"name": n, "pages": c, "see": pages_of(i)} for i, n, c in ents("bank")],
           "people": [{"name": n, "pages": c, "see": pages_of(i)} for i, n, c in ents("person") if not n.startswith("private person")],
           "hubs": [{"name": n, "kind": k.replace("money_", ""), "accounts": links, "see": pages_of(i)} for i, n, k, links in hubs()]}
    return out
