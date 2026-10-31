# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""💶 A user's money: spendings, incomes, the fixed ones of every month, budgets and a monthly saving goal (owner,
1 Nov: «metterei la possibilità di aggiungere le spese... di gestire entrate stipendio e uscite fisse, e grafici che
indicano un andamento con magari un obiettivo di risparmio mensile... utile, completa ma semplice da gestire»).

One SQLite file per user (AURORA_EXPENSES_DIR/expenses.db, mode 600), written by the expenses plugin (what the user
tells in the chat) and by the page (api/money). Amounts in cents: sums never drift. What a movement was and how it was
paid are sealed with the user's «expenses» key (N64, C458); day, amount and category stay plain, so a month's sums are
made in SQL.

A fixed item (the salary, the rent, a subscription) is a template with its day of the month: every month from its
start, once that day has come, it becomes a movement of its own (unique per item and month) — a fixed item changed or
stopped never rewrites the months gone, and a fixed movement deleted by hand is not made again that month.
"""
from __future__ import annotations

import calendar
import os
import re
import sqlite3
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

from . import sys_config, sys_seal

OUT = ("casa", "spesa", "bollette", "trasporti", "auto", "salute", "svago", "ristoranti", "viaggi", "abbigliamento",
       "tecnologia", "abbonamenti", "regali", "tasse", "altro")
IN = ("stipendio", "pensione", "rimborsi", "vendite", "regali", "altro")
KINDS = {"out": ("expenses", OUT), "in": ("incomes", IN)}
DDL = """
CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY, day TEXT NOT NULL, cents INTEGER NOT NULL,
    what TEXT NOT NULL, category TEXT NOT NULL, payment TEXT NOT NULL DEFAULT '', created REAL NOT NULL);
CREATE INDEX IF NOT EXISTS expenses_day ON expenses(day);
CREATE TABLE IF NOT EXISTS budgets (category TEXT PRIMARY KEY, cents INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS incomes (id INTEGER PRIMARY KEY, day TEXT NOT NULL, cents INTEGER NOT NULL,
    what TEXT NOT NULL, category TEXT NOT NULL, payment TEXT NOT NULL DEFAULT '', created REAL NOT NULL,
    fixed_id INTEGER);
CREATE INDEX IF NOT EXISTS incomes_day ON incomes(day);
CREATE TABLE IF NOT EXISTS fixed (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, cents INTEGER NOT NULL,
    what TEXT NOT NULL, category TEXT NOT NULL, dom INTEGER NOT NULL, since TEXT NOT NULL, until TEXT,
    created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS fixed_done (fixed_id INTEGER NOT NULL, month TEXT NOT NULL, PRIMARY KEY (fixed_id, month));
CREATE TABLE IF NOT EXISTS prefs (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def file(cfg: sys_config.Config) -> Path:
    d = cfg.path("AURORA_EXPENSES_DIR")
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    return d / "expenses.db"


def currency(cfg: sys_config.Config) -> str:
    return (str(cfg.values.get("AURORA_EXPENSES_CURRENCY") or "EUR").strip().upper())[:3]


@contextmanager
def db(cfg: sys_config.Config, today: date | None = None):
    """The user's file, ready: tables made, the rows of before sealed, the fixed items of the months come applied."""
    f = file(cfg)
    new = not f.exists()
    con = sqlite3.connect(f, timeout=10)
    try:
        if new:
            os.chmod(f, 0o600)
        con.executescript(DDL)
        if "fixed_id" not in {r[1] for r in con.execute("PRAGMA table_info(expenses)")}:
            con.execute("ALTER TABLE expenses ADD COLUMN fixed_id INTEGER")      # a file of before 1 Nov
        _seal_old(cfg, con)
        _apply_fixed(cfg, con, today or date.today())
        yield con
        con.commit()
    finally:
        con.close()


def seal(cfg: sys_config.Config, value: str, col: str) -> str:
    return sys_seal.seal_text(cfg, value, f"expense:{col}", cfg.user, "expenses") if value else value


def unseal(cfg: sys_config.Config, value: str, col: str) -> str:
    return sys_seal.open_text(cfg, value, f"expense:{col}", cfg.user, "expenses") if value else value


def _seal_old(cfg: sys_config.Config, con) -> None:
    """The rows written before N64, sealed once (then VACUUM: their old pages go)."""
    old = [(i, w, p) for i, w, p in con.execute("SELECT id, what, payment FROM expenses")
           if not sys_seal.is_sealed(w) or (p and not sys_seal.is_sealed(p))]
    for i, w, p in old:
        con.execute("UPDATE expenses SET what = ?, payment = ? WHERE id = ?",
                    (w if sys_seal.is_sealed(w) else seal(cfg, w, "what"),
                     p if sys_seal.is_sealed(p) else seal(cfg, p, "payment"), i))
    if old:
        con.commit()
        con.execute("VACUUM")


# ---- what is typed --------------------------------------------------------------------------------------------------
def cents(amount) -> int:
    s = str(amount).strip().replace("€", "").replace(" ", "")
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d{1,2})?", s):        # 1.234,56
        s = s.replace(".", "")
    s = s.replace(",", ".")
    try:
        v = round(float(s) * 100)
    except ValueError:
        raise ValueError(f"amount: a number, e.g. 45.90 ({amount!r})") from None
    if not 0 < v < 10_000_000_00:
        raise ValueError("amount: more than 0")
    return v


def money(cfg: sys_config.Config, c: int) -> str:
    s = f"{abs(c) / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    cur = currency(cfg)
    return f"{'-' if c < 0 else ''}{s} {'€' if cur == 'EUR' else cur}"


def day(raw: str, today: date | None = None) -> str:
    raw, today = (raw or "").strip().lower(), today or date.today()
    if raw in ("", "oggi", "today"):
        return today.isoformat()
    if raw in ("ieri", "yesterday"):
        return (today - timedelta(days=1)).isoformat()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError("day: YYYY-MM-DD, DD/MM/YYYY, oggi or ieri")


def month(raw: str = "", today: date | None = None) -> str:
    raw = (raw or "").strip()
    if not raw:
        return (today or date.today()).strftime("%Y-%m")
    if re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", raw):
        return raw
    m = re.fullmatch(r"(\d{1,2})[/-](\d{4})", raw)
    if m and 1 <= int(m.group(1)) <= 12:
        return f"{m.group(2)}-{int(m.group(1)):02d}"
    raise ValueError("month: YYYY-MM (e.g. 2026-10)")


def category(kind: str, raw: str) -> str:
    c = (raw or "altro").strip().lower()
    return c if c in KINDS[kind][1] else "altro"


def _kind(kind: str) -> str:
    if kind not in KINDS:
        raise ValueError("kind: out (a spending) or in (an income)")
    return kind


def _shift(m: str, n: int) -> str:
    y, mo = divmod(int(m[:4]) * 12 + int(m[5:]) - 1 + n, 12)
    return f"{y}-{mo + 1:02d}"


# ---- movements -------------------------------------------------------------------------------------------------------
def add(cfg: sys_config.Config, kind: str, amount, what: str, cat: str = "altro", when: str = "oggi",
        payment: str = "") -> dict:
    table = KINDS[_kind(kind)][0]
    c, what = cents(amount), (what or "").strip()[:200]
    if not what:
        raise ValueError("what: what the money was for")
    d, k = day(when), category(kind, cat)
    with db(cfg) as con:
        cur = con.execute(f"INSERT INTO {table} (day, cents, what, category, payment, created) VALUES (?,?,?,?,?,?)",
                          (d, c, seal(cfg, what, "what"), k, seal(cfg, (payment or "").strip()[:40], "payment"), time.time()))
    return {"id": cur.lastrowid, "kind": kind, "day": d, "cents": c, "what": what, "category": k}


def remove(cfg: sys_config.Config, kind: str, mid: int) -> None:
    with db(cfg) as con:
        if not con.execute(f"DELETE FROM {KINDS[_kind(kind)][0]} WHERE id = ?", (int(mid),)).rowcount:
            raise KeyError(mid)


def moves(cfg: sys_config.Config, m: str, kind: str | None = None, cat: str = "", limit: int = 500) -> list[dict]:
    """A month's movements, newest first: {"id", "kind", "day", "cents", "what", "category", "payment", "fixed"}."""
    out = []
    with db(cfg) as con:
        for k in ([kind] if kind else list(KINDS)):
            q, args = (f"SELECT id, day, cents, what, category, payment, fixed_id FROM {KINDS[_kind(k)][0]} "
                       "WHERE day LIKE ?"), [f"{m}-%"]
            if cat:
                q, args = q + " AND category = ?", args + [category(k, cat)]
            for i, d, c, w, ca, p, f in con.execute(q, args):
                out.append({"id": i, "kind": k, "day": d, "cents": c, "what": unseal(cfg, w, "what"), "category": ca,
                            "payment": unseal(cfg, p, "payment"), "fixed": f})
    return sorted(out, key=lambda x: (x["day"], x["id"]), reverse=True)[:limit]


# ---- the fixed ones of every month -------------------------------------------------------------------------------
def fixed_add(cfg: sys_config.Config, kind: str, amount, what: str, cat: str = "altro", dom: int = 1,
              since: str = "") -> dict:
    """A movement of every month on its day (1–31: the month's last day when shorter), from `since` (this month)."""
    c, what = cents(amount), (what or "").strip()[:200]
    if not what:
        raise ValueError("what: what the money is for")
    dom = int(dom)
    if not 1 <= dom <= 31:
        raise ValueError("day of the month: 1 to 31")
    k, start = category(_kind(kind), cat), month(since)
    with db(cfg) as con:
        cur = con.execute("INSERT INTO fixed (kind, cents, what, category, dom, since, created) VALUES (?,?,?,?,?,?,?)",
                          (kind, c, seal(cfg, what, "what"), k, dom, start, time.time()))
        _apply_fixed(cfg, con, date.today())
    return {"id": cur.lastrowid, "kind": kind, "cents": c, "what": what, "category": k, "dom": dom, "since": start}


def fixed_stop(cfg: sys_config.Config, fid: int, today: date | None = None) -> None:
    """No more from next month; the months gone (and this one, if already made) stay."""
    with db(cfg) as con:
        if not con.execute("UPDATE fixed SET until = ? WHERE id = ? AND until IS NULL",
                           (month("", today), int(fid))).rowcount:
            raise KeyError(fid)


def fixed_list(cfg: sys_config.Config) -> list[dict]:
    with db(cfg) as con:
        rows = con.execute("SELECT id, kind, cents, what, category, dom, since FROM fixed WHERE until IS NULL "
                           "ORDER BY kind DESC, dom").fetchall()
    return [{"id": i, "kind": k, "cents": c, "what": unseal(cfg, w, "what"), "category": ca, "dom": d, "since": s}
            for i, k, c, w, ca, d, s in rows]


def _apply_fixed(cfg: sys_config.Config, con, today: date) -> None:
    """Every fixed item's months from its start to today, once its day has come, as movements (each once)."""
    now = today.strftime("%Y-%m")
    for fid, kind, c, w, ca, dom, since, until in con.execute(
            "SELECT id, kind, cents, what, category, dom, since, until FROM fixed").fetchall():
        m, last = since, min(now, until) if until else now
        while m <= last:
            y, mo = int(m[:4]), int(m[5:])
            d = date(y, mo, min(dom, calendar.monthrange(y, mo)[1]))
            if d <= today and not con.execute("SELECT 1 FROM fixed_done WHERE fixed_id = ? AND month = ?", (fid, m)).fetchone():
                con.execute(f"INSERT INTO {KINDS[kind][0]} (day, cents, what, category, payment, created, fixed_id) "
                            "VALUES (?,?,?,?,?,?,?)", (d.isoformat(), c, w, ca, "", time.time(), fid))
                con.execute("INSERT INTO fixed_done VALUES (?, ?)", (fid, m))
            m = _shift(m, 1)


# ---- budgets, the goal, the month and the trend -------------------------------------------------------------------
def set_budget(cfg: sys_config.Config, cat: str, monthly) -> int:
    """A category's monthly budget in cents (0 removes it)."""
    c = category("out", cat)
    with db(cfg) as con:
        if str(monthly).strip() in ("0", "0.0", "0,0", ""):
            con.execute("DELETE FROM budgets WHERE category = ?", (c,))
            return 0
        v = cents(monthly)
        con.execute("INSERT INTO budgets VALUES (?, ?) ON CONFLICT(category) DO UPDATE SET cents = excluded.cents", (c, v))
    return v


def set_goal(cfg: sys_config.Config, monthly) -> int:
    """The monthly saving goal in cents (0 removes it)."""
    v = 0 if str(monthly).strip() in ("0", "0.0", "0,0", "") else cents(monthly)
    with db(cfg) as con:
        con.execute("INSERT INTO prefs VALUES ('goal', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (str(v),))
    return v


def _sums(con, table: str, m: str) -> dict[str, int]:
    return dict(con.execute(f"SELECT category, SUM(cents) FROM {table} WHERE day LIKE ? GROUP BY category", (f"{m}-%",)))


def trend(cfg: sys_config.Config, end: str = "", n: int = 12) -> list[dict]:
    """The last `n` months to `end`: {"month", "income", "spent", "saved"} in cents."""
    last = month(end)
    out = []
    with db(cfg) as con:
        for m in (_shift(last, -i) for i in range(n - 1, -1, -1)):
            i, s = sum(_sums(con, "incomes", m).values()), sum(_sums(con, "expenses", m).values())
            out.append({"month": m, "income": i, "spent": s, "saved": i - s})
    return out


def view(cfg: sys_config.Config, m: str = "") -> dict:
    """What the page shows for a month: the totals, the goal, the categories with their budgets, the movements, the
    fixed items and the year's trend."""
    m = month(m)
    with db(cfg) as con:
        spent, before = _sums(con, "expenses", m), _sums(con, "expenses", _shift(m, -1))
        income = _sums(con, "incomes", m)
        budgets = dict(con.execute("SELECT category, cents FROM budgets"))
        goal = int((con.execute("SELECT value FROM prefs WHERE key = 'goal'").fetchone() or ["0"])[0])
    cats = [{"category": c, "cents": v, "budget": budgets.get(c)} for c, v in sorted(spent.items(), key=lambda kv: -kv[1])]
    cats += [{"category": c, "cents": 0, "budget": b} for c, b in budgets.items() if c not in spent]
    i, s = sum(income.values()), sum(spent.values())
    return {"month": m, "currency": currency(cfg), "income": i, "spent": s, "saved": i - s, "goal": goal,
            "spent_before": sum(before.values()), "categories": cats,
            "incomes": [{"category": c, "cents": v} for c, v in sorted(income.items(), key=lambda kv: -kv[1])],
            "moves": moves(cfg, m), "fixed": fixed_list(cfg), "trend": trend(cfg, m),
            "choices": {"out": list(OUT), "in": list(IN)}}


def summary_text(cfg: sys_config.Config, m: str = "") -> str:
    """The month in words, for the chat: incomes, spendings by category with the budgets passed, what is saved
    against the goal and the month before."""
    v = view(cfg, m)
    if not v["income"] and not v["spent"]:
        return f"no movements in {v['month']}"
    rows = [f"Mese {v['month']}: entrate {money(cfg, v['income'])}, uscite {money(cfg, v['spent'])}"
            + (f" (mese prima {money(cfg, v['spent_before'])}, {(v['spent'] - v['spent_before']) / v['spent_before']:+.0%})"
               if v["spent_before"] else "")
            + f", risparmio {money(cfg, v['saved'])}"
            + (f" su un obiettivo di {money(cfg, v['goal'])}{' ✅' if v['saved'] >= v['goal'] else ''}" if v["goal"] else "")]
    for c in v["categories"]:
        if c["cents"]:
            b = c["budget"]
            rows.append(f"- {c['category']}: {money(cfg, c['cents'])} ({c['cents'] / v['spent']:.0%})"
                        + (f" · budget {money(cfg, b)}{' ⚠️ superato' if c['cents'] > b else ''}" if b else ""))
    return "\n".join(rows)
