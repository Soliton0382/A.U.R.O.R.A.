# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""What the forge looks at before it writes a plugin (moved from agt_forge, 7 October 2026: one module per part):
the data a need points to (peek: never .env, the vault, the memory or the owner's files), the time window it asks for,
the levels and kinds of a log's lines, and the places of data the forge may mention."""
from __future__ import annotations

import re
import time
from pathlib import Path

from . import sys_config
from .agt_forge import NEVER


def _others(cfg: sys_config.Config, p: Path) -> bool:
    """Another user's things, or the users store: never looked at by the forge working for this user (multi-user)."""
    from . import sys_users_layout as L
    base = cfg.base or cfg
    m = L.migrated(base)
    if not m:
        return False
    me = cfg.user or m["admin"]
    if p == base.path("AURORA_STATUS_DIR") / "users.db":
        return True
    others = L._registered(base) - {me}
    homes = [L.usr(base) / o for o in others] + [L.root(base, a) / L.USERS / o for a in L.SYS_AREAS for o in others]
    return any(p == h or h in p.parents for h in homes)


def peek(cfg: sys_config.Config, paths: list[str], hours: float = 24) -> str:
    """What the forge may look at: a folder's listing or a file's first lines, inside Aurora's folder, never NEVER.
    A log's kinds are counted over the need's window (`hours`), its rotated copies included (A20)."""
    root = cfg.root.resolve()
    out = []
    for rel in paths[:3]:
        rel = str(rel).strip().lstrip("/")
        p = (root / rel).resolve()
        if (root not in p.parents and p != root or any(rel == n or rel.startswith(n + "/") or n in p.parts for n in NEVER)
                or _others(cfg, p)):
            out.append(f"## {rel}\n(not allowed)")
            continue
        if p.is_dir() and any(x.is_dir() for x in p.iterdir()):
            # a folder of folders (sys/logs: one per component): each one's newest file, its rotated copies of the
            # window included, counted by level over the need's window, and one example line per format (A20)
            rows, formats = [], {}
            for sub in sorted(x for x in p.iterdir() if x.is_dir())[:30]:
                files = sorted((x for x in sub.iterdir() if x.is_file() and not x.name.endswith(".gz")), key=lambda x: -x.stat().st_mtime)
                if not files:
                    continue
                newest = files[0]
                with open(newest, "rb") as h:
                    h.seek(max(0, newest.stat().st_size - 20_000_000))
                    lines = h.read().decode(errors="replace").splitlines()[1:]
                lines = _rotated(newest, time.time() - hours * 3600 - 3600) + lines
                rows.append(f"{sub.name}/{newest.name}: {levels_of(lines, hours)}")
                if lines:
                    formats.setdefault(_shape(lines[-1])[:20], f"{sub.name}/{newest.name}: {lines[-1][:220]}")
            out.append(f"## {rel}/ (one folder per component; lines per level, counted by code over the live log and its "
                       f"rotated copies)\n" + "\n".join(rows) + "\n## example lines, one per format\n"
                       + "\n".join(list(formats.values())[:8]))
            continue
        if p.is_dir():
            items = sorted(p.iterdir(), key=lambda x: -x.stat().st_mtime)[:25]
            out.append(f"## {rel}/ (newest first)\n" + "\n".join(f"{x.name}{'/' if x.is_dir() else ''} {x.stat().st_size} B" for x in items))
            newest = next((x for x in items if x.is_file()), None)
            if newest is not None:                           # the real line format, not only the names (M53)
                p, rel = newest, f"{rel}/{newest.name}"
        if p.is_file():
            import gzip
            if p.suffix == ".gz":
                with gzip.open(p, "rt", errors="replace") as h:
                    out.append(f"## {rel} (first lines)\n{h.read(3000)}")
            else:                                            # a log: its start and, above all, its latest lines
                size = p.stat().st_size
                with open(p, "rb") as h:
                    head = h.read(800).decode(errors="replace")
                    h.seek(max(0, size - 20_000_000))
                    recent = h.read().decode(errors="replace").splitlines()[1:]
                recent = _rotated(p, time.time() - hours * 3600 - 3600) + recent
                out.append(f"## {rel} (first lines)\n{head}\n...\n## {rel} ({len(recent)} lines read, rotated copies of the "
                           f"window included; one line of each kind, with counts)\n"
                           + "\n".join(kinds_of(recent, hours=hours))[:4000] if size > 3800 else f"## {rel}\n{head}")
        else:
            out.append(f"## {rel}\n(not found)")
    return "\n\n".join(out)


WINDOW = (  # the time window a need asks for, in hours (A20: the judge counted 24 h whatever the need said)
    (r"(?:ultim[aoie]|last|past)\s+(\d+)\s*(?:or[ae]|hours?|h)\b", 1),
    (r"(?:ultim[aoie]|last|past)\s+(\d+)\s*(?:giorn[oi]|days?)\b", 24),
    (r"(?:ultim[aoie]|last|past)\s+(\d+)\s*(?:settiman[ae]|weeks?)\b", 168),
    (r"(?:ultim[ao]|last|past)\s+or[ae]\b|(?:last|past)\s+hour\b", "1"),
    (r"(?:ultim[ao]|last|past)\s+giorn[oi]\b|(?:last|past)\s+day\b|\boggi\b|\btoday\b", "24"),
    (r"(?:ultim[ao]|last|past)\s+settimana\b|(?:last|past)\s+week\b", "168"),
    (r"(?:ultim[ao]|last|past)\s+mese\b|(?:last|past)\s+month\b", "720"),
)


def window_hours(need: str, default: float | None = None) -> float | None:
    """«nelle ultime 6 ore» → 6, «negli ultimi 7 giorni» → 168, «nell'ultima settimana» → 168; no window asked: `default`
    (None: the judge is not told of a window the need does not have). Pure."""
    text = need.lower()
    for rx, unit in WINDOW:
        m = re.search(rx, text)
        if m:
            return float(unit) if isinstance(unit, str) else float(m.group(1)) * unit
    return default


def _rotated(path: Path, since: float) -> list[str]:
    """The lines of a log's rotated copies (<stem>.<time>.<ext>.gz) changed since `since`: a window often spans
    several files, and counting only the live one gave the judge wrong facts (C94, A20)."""
    import gzip
    stem, ext = path.name.rsplit(".", 1) if "." in path.name else (path.name, "")
    out = []
    for f in sorted(path.parent.glob(f"{stem}.*.{ext}.gz" if ext else f"{stem}.*.gz")):
        if f.stat().st_mtime >= since:
            with gzip.open(f, "rt", errors="replace") as h:
                out += h.read().splitlines()
    return out


LEVEL = re.compile(r"\b(DEBUG|INFO|WARNING|WARN|ERROR|CRITICAL)\b|\"level\"\s*:\s*\"(\w+)\"", re.I)


def _when(line: str):
    """A log line's time: ISO at its start, or a JSON "ts" in seconds (Caddy); None when it has none."""
    import datetime as dt
    try:
        return dt.datetime.fromisoformat(line[:29])
    except ValueError:
        m = re.search(r"\"ts\"\s*:\s*(\d{9,11}(?:\.\d+)?)", line[:200])
        return dt.datetime.fromtimestamp(float(m.group(1))).astimezone() if m else None


def levels_of(lines: list[str], hours: float) -> str:
    """Lines per level in the window and in all (WARNING and WARN are one level; JSON "level" too): facts for the
    judge of a tool that counts by level (A20). Pure."""
    import datetime as dt
    from collections import Counter
    since = dt.datetime.now().astimezone() - dt.timedelta(hours=hours)
    inside, total = Counter(), Counter()
    for line in lines:
        m = LEVEL.search(line[:300])
        if not m:
            continue
        lvl = (m.group(1) or m.group(2)).upper().replace("WARN", "WARNING").replace("WARNINGING", "WARNING")
        total[lvl] += 1
        w = _when(line)
        if w is not None and w >= since:
            inside[lvl] += 1
    fmt = lambda c: ", ".join(f"{k} {v}" for k, v in sorted(c.items())) or "none"  # noqa: E731
    bad = lambda c: c["WARNING"] + c["ERROR"] + c["CRITICAL"]  # noqa: E731
    return (f"in the last {hours:g} h: {fmt(inside)} (WARNING+ERROR+CRITICAL = {bad(inside)}); in all: {fmt(total)} "
            f"(WARNING+ERROR+CRITICAL = {bad(total)})")


def _dated(line: str) -> bool:
    import datetime as dt
    try:
        dt.datetime.fromisoformat(line[:29])
        return True
    except ValueError:
        return False


def _shape(line: str) -> str:
    shape = re.sub(r"\d+", "9", re.sub(r"\"[^\"]*\"|'[^']*'", "''", line))
    words = re.sub(r"\s+", " ", shape)[:90].split()     # time, level, component, then the first own token
    return " ".join(w if len(w) < 20 else w.split(":")[0][:12] + ":W" for w in words[:4])


def kinds_of(lines: list[str], most: int = 20, hours: float = 24) -> list[str]:
    """One recent line per shape (digits, ids and quoted text folded), each with how many lines of that shape the
    data has in the last `hours` and in all: a sample that shows the rare kinds too, and facts a judge can check
    counts against (M53). Pure."""
    import datetime as dt
    since = dt.datetime.now().astimezone() - dt.timedelta(hours=hours)
    counts: dict[str, list] = {}
    for line in lines:
        k = _shape(line)
        c = counts.setdefault(k, [0, 0, line])
        c[1] += 1
        c[2] = line
        try:
            if dt.datetime.fromisoformat(line[:29]) >= since:
                c[0] += 1
        except ValueError:
            pass
    top = sorted(counts.values(), key=lambda c: -c[1])[:most]
    dated = sum(c[0] for c in counts.values()) or any(_dated(c[2]) for c in counts.values())
    if not dated:                     # no time at the start of the lines (a JSON file): no window to count by (A20)
        return [f"# kind: {total} lines in all (the lines carry no time at their start: count the window from the "
                f"data's own time fields); an example line follows\n{line[:260]}" for _, total, line in top]
    # the facts on their own line: the example below them is the log line exactly as it is (M53: a prefix on the same
    # line made the forge parse "[N lines...]" as part of the format)
    return [f"# kind: {recent} lines in the last {hours:g} h, {total} in all; an example line follows\n{line[:260]}"
            for recent, total, line in top]


def data_places(cfg: sys_config.Config) -> str:
    """The folders the forge can mention, from the settings schema (paths only, with what they hold)."""
    rows = []
    for s in sys_config.load_schema()["settings"]:
        if s.get("type") == "path" and not s.get("secret"):
            try:
                rel = cfg.path(s["key"]).resolve().relative_to(cfg.root.resolve())
            except (ValueError, KeyError):                  # outside Aurora's folder, or a key this config predates
                continue
            if not any(str(rel).startswith(n) for n in NEVER):
                rows.append(f"- {rel}: {s.get('en', '')[:140]}")
    from . import sys_users_layout                       # this user's own state (routines, approvals): its real place
    state = sys_users_layout.place(cfg, "state", cfg.user)
    try:
        rows.append(f"- {state.relative_to(cfg.root.resolve())}: this user's routines.json, approvals.json, react.json")
    except ValueError:
        pass
    return "\n".join(rows[:41])
