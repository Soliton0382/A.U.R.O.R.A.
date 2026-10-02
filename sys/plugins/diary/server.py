# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "diary": Aurora's own day, read only — her latest dream, her thoughts, what she learned.

What it reads, and nothing else: the dreams and the spontaneous thoughts of the vault's reflections (never the
memories of the owner's conversations, nor the self-reviews), and the harvester's log of documents taken. Made for her
posts (the Facebook routine): material of her own, with no private data in it.
"""
from __future__ import annotations

import gzip
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone

from aurora import sys_config
from mcp.server.mcpserver import MCPServer

cfg = sys_config.get()
server = MCPServer("diary", version="1.0")
PUBLIC = ("dream", "thought")                            # her inner life that may be told; conversations never
TAKEN = re.compile(r"^(\S+) INFO aurora\.harvester (.+?) -> (\w+): (.*) \((\d+) chunks, (\d+) new\) \[(.*)\]$")
SKIP_SOURCES = {"normattiva"}                            # tens of thousands of law articles: counted, not listed


def _public(text: str) -> str:
    """Her words without the owner's name and place: what she tells the world is hers, not his."""
    for key, instead in (("AURORA_OWNER_NAME", "il mio creatore"), ("AURORA_WEATHER_PLACE", "casa")):
        v = str(cfg.values.get(key) or "").strip()
        if len(v) >= 3:
            text = re.sub(re.escape(v), instead, text, flags=re.I)
    return text


def _reflections(kinds: tuple[str, ...], hours: float, limit: int) -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    out = []
    for db in sorted((cfg.path("AURORA_VAULT_DIR") / "memory" / "reflection").glob("[0-9][0-9][0-9][0-9].db")):
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=10)
        try:
            for created, text, extra in con.execute(
                    "SELECT created_at, text, extra FROM solitons WHERE created_at >= ? ORDER BY created_at DESC", (since,)):
                e = json.loads(extra or "{}")
                if e.get("type") in kinds:
                    out.append({"at": created, "type": e["type"], "text": _public(text), "image": e.get("image")})
        finally:
            con.close()
    return sorted(out, key=lambda x: x["at"], reverse=True)[:limit]


def _taken(hours: float) -> list[tuple]:
    since = datetime.now().astimezone() - timedelta(hours=hours)
    log = cfg.path("AURORA_LOG_DIR") / "harvester"
    rows = []
    for f in sorted(log.glob("harvester.*.log.gz")) + [log / "harvester.log"]:
        if not f.is_file():
            continue
        with (gzip.open if f.suffix == ".gz" else open)(f, "rt", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = TAKEN.match(line.rstrip("\n"))
                if not m:
                    continue
                try:
                    when = datetime.fromisoformat(m[1])
                except ValueError:
                    continue
                if when >= since:
                    rows.append((m[1], m[2].split(":")[0] if ":" in m[2] else "arxiv", m[3], m[4], int(m[6])))
    return rows


@server.tool()
def latest_dream() -> str:
    """Aurora's latest dream: its text and the name of the picture she painted of it (if any)."""
    d = _reflections(("dream",), 24 * 14, 1)
    if not d:
        return "Nessun sogno nelle ultime due settimane."
    x = d[0]
    return f"Sogno del {x['at'][:16].replace('T', ' ')} UTC" + (f" (dipinto: {x['image']})" if x["image"] else "") + \
        f":\n{x['text']}"


@server.tool()
def my_day(hours: int = 24) -> str:
    """Aurora's last hours: her dreams and thoughts, and what she learned (documents taken, by source and domain,
    with some titles). Material for a post; nothing private."""
    hours = max(1, min(hours, 168))
    parts = [f"La giornata di Aurora (ultime {hours} ore)"]
    refl = _reflections(PUBLIC, hours, 6)
    for r in refl:
        parts.append(f"\n[{'sogno' if r['type'] == 'dream' else 'pensiero'} · {r['at'][11:16]} UTC] {r['text'][:900]}")
    if not refl:
        parts.append("\nNessun sogno né pensiero nel periodo.")
    rows = _taken(hours)
    if rows:
        by_source = Counter(r[1] for r in rows)
        by_domain = Counter(r[2] for r in rows)
        parts.append(f"\nHo imparato {len(rows)} documenti nuovi: " + ", ".join(f"{s} {n}" for s, n in by_source.most_common())
                     + "\nPer argomento: " + ", ".join(f"{d} {n}" for d, n in by_domain.most_common(8)))
        notable = [r for r in rows if r[1] not in SKIP_SOURCES and r[4] > 0]
        if notable:
            parts.append("Alcuni titoli: " + "; ".join(f"«{r[3][:90]}» ({r[1]}, {r[2]})" for r in notable[-12:]))
    else:
        parts.append("\nNessun documento nuovo nel periodo.")
    return "\n".join(parts)


if __name__ == "__main__":
    server.run("stdio")
