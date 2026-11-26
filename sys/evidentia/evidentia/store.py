# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The archive on disk: SQLite, no server, no port (PLAN: «Lo schema»). Three files in EVD_DATA_DIR:
  corpus.db    documents, pages, passages (+ FTS5 in English: porter), images — what the government released
  findings.db  entities and their mentions, identifiers, events, the global registry of relations, cards
  cases.db     the case files (= the chats), their diary of steps, their table, their group; the leads (each done once)
Every row knows where it comes from (collection, number, page, place in the text). WAL: one writer, many readers."""
from __future__ import annotations

import sqlite3
from pathlib import Path

CORPUS = """
CREATE TABLE IF NOT EXISTS documents (
  doc TEXT PRIMARY KEY,            -- collection:number (ABC:ABC0001234)
  collection TEXT NOT NULL, number TEXT NOT NULL, path TEXT NOT NULL UNIQUE,
  sha256 TEXT, bytes INTEGER, mtime REAL, pages INTEGER,
  kind TEXT,                       -- text, scan, mixed (PDFs); image (read by OCR)
  official_url TEXT,
  status TEXT NOT NULL DEFAULT 'new',   -- new, text, indexed, failed
  error TEXT
);
CREATE TABLE IF NOT EXISTS pages (
  doc TEXT NOT NULL, page INTEGER NOT NULL, text TEXT, chars INTEGER, source TEXT,   -- pdf or ocr
  PRIMARY KEY (doc, page)
);
CREATE TABLE IF NOT EXISTS passages (
  id INTEGER PRIMARY KEY, doc TEXT NOT NULL, page INTEGER NOT NULL, start INTEGER, end INTEGER, text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS passages_doc ON passages(doc, page);
CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts USING fts5(text, content='passages', content_rowid='id',
  tokenize='porter unicode61');
CREATE TRIGGER IF NOT EXISTS passages_ai AFTER INSERT ON passages BEGIN
  INSERT INTO passages_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS passages_ad AFTER DELETE ON passages BEGIN
  INSERT INTO passages_fts(passages_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
CREATE TABLE IF NOT EXISTS images (
  doc TEXT NOT NULL, page INTEGER NOT NULL, idx INTEGER NOT NULL,
  category TEXT,                   -- document, marked_object, people, excluded, place
  doc_type TEXT,                   -- bill_of_lading, invoice, flight_log, note, … (documents only)
  text TEXT, note TEXT,            -- people and excluded: never a description
  PRIMARY KEY (doc, page, idx)
);
"""
FINDINGS = """
CREATE TABLE IF NOT EXISTS entities (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL,   -- person, org, place, aircraft, vessel, account…
  protected INTEGER NOT NULL DEFAULT 0,                             -- a victim or a redacted name: never shown, never crossed
  UNIQUE (name, kind)
);
CREATE TABLE IF NOT EXISTS aliases (entity INTEGER NOT NULL, alias TEXT NOT NULL, PRIMARY KEY (entity, alias));
CREATE TABLE IF NOT EXISTS mentions (
  entity INTEGER NOT NULL, doc TEXT NOT NULL, page INTEGER NOT NULL, start INTEGER, end INTEGER, role TEXT
);
CREATE INDEX IF NOT EXISTS mentions_entity ON mentions(entity);
CREATE INDEX IF NOT EXISTS mentions_doc ON mentions(doc, page);
CREATE TABLE IF NOT EXISTS identifiers (
  kind TEXT NOT NULL, value TEXT NOT NULL, valid INTEGER NOT NULL,
  doc TEXT NOT NULL, page INTEGER NOT NULL, start INTEGER, end INTEGER
);
CREATE INDEX IF NOT EXISTS identifiers_value ON identifiers(kind, value);
CREATE INDEX IF NOT EXISTS identifiers_doc ON identifiers(doc, page);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY, day TEXT, place TEXT, what TEXT NOT NULL, who TEXT, doc TEXT NOT NULL, page INTEGER NOT NULL,
  kind TEXT                        -- fact, testimony, accusation
);
CREATE TABLE IF NOT EXISTS relations (
  id INTEGER PRIMARY KEY, a INTEGER NOT NULL, b INTEGER NOT NULL,
  kind TEXT NOT NULL,              -- same_identifier, same_flight, payment, communication, deposition, …
  strength TEXT NOT NULL,          -- strong (same identifier), medium (name and date), weak (name)
  evidence TEXT NOT NULL,          -- JSON: [{doc, page, start, end, why}]
  verified_by TEXT, found_in_case TEXT, created REAL,
  UNIQUE (a, b, kind)
);
CREATE TABLE IF NOT EXISTS cards (
  doc TEXT PRIMARY KEY, kind TEXT, days TEXT, who TEXT, identifiers TEXT, summary TEXT, key_pages TEXT, written REAL
);
"""
CASES = """
CREATE TABLE IF NOT EXISTS cases (
  id TEXT PRIMARY KEY, title TEXT NOT NULL, grp TEXT, created REAL, updated REAL, archived INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS steps (
  id INTEGER PRIMARY KEY, case_id TEXT NOT NULL, at REAL NOT NULL,
  kind TEXT NOT NULL,              -- question, plan, search, read, claim, relation, lead, answer, note
  content TEXT NOT NULL,           -- JSON
  docs TEXT                        -- JSON list of collection:number touched by the step
);
CREATE INDEX IF NOT EXISTS steps_case ON steps(case_id, id);
CREATE TABLE IF NOT EXISTS tables (case_id TEXT PRIMARY KEY, goal TEXT, open_points TEXT, evidence TEXT, leads TEXT);
-- the leads: the archive's registry of work, each done once (leads.py), and the cases subscribed to each
CREATE TABLE IF NOT EXISTS leads (
  id INTEGER PRIMARY KEY,
  key TEXT NOT NULL UNIQUE,        -- the work: agent + the target's words, normalized (the same work is done once)
  agent TEXT NOT NULL, what TEXT NOT NULL, why TEXT, docs TEXT,      -- docs: JSON list of collection:number
  case_id TEXT NOT NULL,           -- the case that opened it
  parent INTEGER, depth INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'open',
  worker TEXT, lease_until REAL, lease_hash TEXT,   -- the lease's token, hashed: only its holder reports
  summary TEXT, evidence TEXT,     -- JSON: [{doc, page, quote, note, cite}], every quote checked on its page
  created REAL NOT NULL, finished REAL
);
CREATE INDEX IF NOT EXISTS leads_status ON leads(status, id);
CREATE TABLE IF NOT EXISTS lead_cases (lead INTEGER NOT NULL, case_id TEXT NOT NULL, since REAL NOT NULL,
  PRIMARY KEY (lead, case_id));
"""
SCHEMAS = {"corpus.db": CORPUS, "findings.db": FINDINGS, "cases.db": CASES}


def connect(data_dir: Path, name: str, readonly: bool = False) -> sqlite3.Connection:
    p = Path(data_dir) / name
    if readonly:
        con = sqlite3.connect(f"file:{p}?mode=ro", uri=True, check_same_thread=False)
    else:
        p.parent.mkdir(parents=True, exist_ok=True)
        # 60 s for another writer (27 Nov: the OCR of C751 and a folder read in from the WebUI write the same corpus; the
        # default 5 s made the second one fail with «database is locked»)
        con = sqlite3.connect(p, check_same_thread=False, timeout=60)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
    con.row_factory = sqlite3.Row
    return con


def create(data_dir: Path, only: str = "") -> list[str]:
    """Every database made (or brought to the schema), or only the one named: idempotent. The corpus is opened
    read-write only here, never by a request that needs the case files alone (audit, 10 Nov)."""
    names = [only] if only else list(SCHEMAS)
    for name in names:
        con = connect(data_dir, name)
        con.executescript(SCHEMAS[name])
        for table, column, kind in MIGRATIONS.get(name, ()):
            if column not in {r[1] for r in con.execute(f"PRAGMA table_info({table})")}:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")
        con.commit()
        con.close()
    return names


# columns added after a database was first made: (table, column, type)
MIGRATIONS = {"cases.db": (("leads", "lease_hash", "TEXT"),)}
