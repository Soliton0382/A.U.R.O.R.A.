# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "expenses": the owner's spending, kept on this machine only (AURORA_EXPENSES_DIR/expenses.db, mode 600).

"Ho speso 45 € di benzina" becomes a row (amount, what, category, day); the owner asks for a month, a category, a
summary against the month before and against his monthly budgets. No network (sandbox), writes only its folder.
Amounts are kept in cents (integers): sums never drift.
"""
from __future__ import annotations

import os
import re
import sqlite3
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

from aurora import sys_config
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

cfg = sys_config.get()
CURRENCY = (str(cfg.values.get("AURORA_EXPENSES_CURRENCY") or "EUR").strip().upper())[:3]
CATEGORIES = ("casa", "spesa", "trasporti", "auto", "salute", "svago", "ristoranti", "viaggi", "abbigliamento",
              "tecnologia", "abbonamenti", "regali", "tasse", "altro")
DDL = """
CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY, day TEXT NOT NULL, cents INTEGER NOT NULL,
    what TEXT NOT NULL, category TEXT NOT NULL, payment TEXT NOT NULL DEFAULT '', created REAL NOT NULL);
CREATE INDEX IF NOT EXISTS expenses_day ON expenses(day);
CREATE TABLE IF NOT EXISTS budgets (category TEXT PRIMARY KEY, cents INTEGER NOT NULL);
"""
server = MCPServer("expenses", version="1.0")


def _file() -> Path:
    raw = str(cfg.values.get("AURORA_EXPENSES_DIR") or "usr/expenses").strip()
    d = Path(raw) if Path(raw).is_absolute() else cfg.root / raw
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    return d / "expenses.db"


@contextmanager
def _db():
    f = _file()
    new = not f.exists()
    con = sqlite3.connect(f, timeout=10)
    try:
        if new:
            os.chmod(f, 0o600)
        con.executescript(DDL)
        yield con
        con.commit()
    finally:
        con.close()


def _cents(amount) -> int:
    s = str(amount).strip().replace("€", "").replace(" ", "")
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d{1,2})?", s):        # 1.234,56
        s = s.replace(".", "")
    s = s.replace(",", ".")
    try:
        v = round(float(s) * 100)
    except ValueError:
        raise ToolError(f"amount: a number, e.g. 45.90 ({amount!r})") from None
    if not 0 < v < 10_000_000_00:
        raise ToolError("amount: more than 0")
    return v


def _money(cents: int) -> str:
    s = f"{cents / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} {'€' if CURRENCY == 'EUR' else CURRENCY}"


def _day(raw: str) -> str:
    raw = (raw or "").strip().lower()
    today = date.today()
    if raw in ("", "oggi", "today"):
        return today.isoformat()
    if raw in ("ieri", "yesterday"):
        return (today - timedelta(days=1)).isoformat()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            pass
    raise ToolError("day: YYYY-MM-DD, DD/MM/YYYY, oggi or ieri")


def _month(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return date.today().strftime("%Y-%m")
    if re.fullmatch(r"\d{4}-\d{2}", raw):
        return raw
    m = re.fullmatch(r"(\d{1,2})[/-](\d{4})", raw)
    if m:
        return f"{m.group(2)}-{int(m.group(1)):02d}"
    raise ToolError("month: YYYY-MM (e.g. 2026-10)")


def _cat(raw: str) -> str:
    c = (raw or "altro").strip().lower()
    return c if c in CATEGORIES else "altro"


@server.tool()
def expense_add(amount: str, what: str, category: str = "altro", day: str = "oggi", payment: str = "") -> str:
    """Record a spending: amount (e.g. 45.90), what it was, category (one of: casa, spesa, trasporti, auto, salute,
    svago, ristoranti, viaggi, abbigliamento, tecnologia, abbonamenti, regali, tasse, altro), day, how it was paid."""
    cents, what = _cents(amount), (what or "").strip()[:200]
    if not what:
        raise ToolError("what: what the money was for")
    d, c = _day(day), _cat(category)
    with _db() as con:
        cur = con.execute("INSERT INTO expenses (day, cents, what, category, payment, created) VALUES (?,?,?,?,?,?)",
                          (d, cents, what, c, (payment or "").strip()[:40], time.time()))
    return f"recorded #{cur.lastrowid}: {_money(cents)} · {what} · {c} · {d}"


@server.tool()
def expense_list(month: str = "", category: str = "", limit: int = 50) -> str:
    """The spendings of a month (default this one), optionally of one category, newest first."""
    m = _month(month)
    q, args = "SELECT id, day, cents, what, category, payment FROM expenses WHERE day LIKE ?", [f"{m}-%"]
    if category:
        q, args = q + " AND category = ?", args + [_cat(category)]
    with _db() as con:
        rows = con.execute(q + " ORDER BY day DESC, id DESC LIMIT ?", args + [max(1, min(limit, 500))]).fetchall()
    if not rows:
        return f"no spendings in {m}" + (f" for {category}" if category else "")
    return "\n".join(f"#{i} {d} · {_money(c)} · {w} · {cat}" + (f" · {p}" if p else "") for i, d, c, w, cat, p in rows)


@server.tool()
def expense_summary(month: str = "") -> str:
    """A month by category, the total, the change against the month before and the budgets passed."""
    m = _month(month)
    y, mo = int(m[:4]), int(m[5:])
    prev = f"{y - 1}-12" if mo == 1 else f"{y}-{mo - 1:02d}"
    with _db() as con:
        cur = dict(con.execute("SELECT category, SUM(cents) FROM expenses WHERE day LIKE ? GROUP BY category", (f"{m}-%",)))
        before = dict(con.execute("SELECT category, SUM(cents) FROM expenses WHERE day LIKE ? GROUP BY category", (f"{prev}-%",)))
        budgets = dict(con.execute("SELECT category, cents FROM budgets"))
    if not cur:
        return f"no spendings in {m}"
    total, total_before = sum(cur.values()), sum(before.values())
    rows = [f"Spese di {m}: {_money(total)}" + (f" (mese prima {_money(total_before)}, "
                                                 f"{(total - total_before) / total_before:+.0%})" if total_before else "")]
    for c, v in sorted(cur.items(), key=lambda kv: -kv[1]):
        b = budgets.get(c)
        rows.append(f"- {c}: {_money(v)} ({v / total:.0%})" + (f" · budget {_money(b)}{' ⚠️ superato' if v > b else ''}" if b else ""))
    return "\n".join(rows)


@server.tool()
def expense_budget(category: str, monthly: str) -> str:
    """Set the monthly budget of a category (0 removes it); the summary says when it is passed."""
    c = _cat(category)
    with _db() as con:
        if str(monthly).strip() in ("0", "0.0", "0,0", ""):
            con.execute("DELETE FROM budgets WHERE category = ?", (c,))
            return f"budget of {c} removed"
        cents = _cents(monthly)
        con.execute("INSERT INTO budgets VALUES (?, ?) ON CONFLICT(category) DO UPDATE SET cents = excluded.cents", (c, cents))
    return f"budget of {c}: {_money(cents)} a month"


@server.tool()
def expense_delete(expense_id: int) -> str:
    """Remove a spending recorded by mistake (its #id from expense_list)."""
    with _db() as con:
        n = con.execute("DELETE FROM expenses WHERE id = ?", (int(expense_id),)).rowcount
    if not n:
        raise ToolError(f"no spending #{expense_id}")
    return f"removed #{expense_id}"


if __name__ == "__main__":
    server.run("stdio")
