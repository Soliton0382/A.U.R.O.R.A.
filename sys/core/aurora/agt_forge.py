# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The capability forge: Aurora builds the plugin she is missing.

 request   an agent finds no tool for what it must do and calls request_capability(need, why): the request is
           queued (status/forge/requests.json), one per need
 build     aurora-rem hands the oldest pending request to aurora-api: the reasoner looks at the data it needs
           (at most 3 files or folders, never .env, the vault, the memory or the owner's files), writes the
           plugin (manifest + MCP server) with its own tests, and the plugin runs them inside the cage; up to 3
           attempts, each with the errors of the last
 decide    read only = every effect "read", no folder it may write, and no network ("sandbox": {"network": false},
           enforced by the cage: --unshare-net): installed and switched on at once, the owner is told, and the
           routine that asked runs again. Anything else (writes, network, sends) waits in Approvals.
The ethics code applies (level A capabilities are refused). Nothing is signed by Aurora: a forged plugin works
and is shown as "made by Aurora, not signed" until the owner signs (sys_ethics_sign.py).
"""
from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from pathlib import Path

from . import sys_config, sys_log

NAME = re.compile(r"^[a-z][a-z0-9_]{2,30}$")
NEVER = (".env", "sys/vault", "usr/uploads", "sys/status/push", "sys/status/plugins/env", "sys/status/devices.json", ".ssh")
TEMPLATE = '''# SPDX-License-Identifier: Apache-2.0
"""Plugin "NAME": one line on what it reads."""
from __future__ import annotations

from aurora import sys_config
from mcp.server.mcpserver import MCPServer

cfg = sys_config.get()                     # cfg.path("AURORA_LOG_DIR") etc.: Aurora's folders, read only here
server = MCPServer("NAME", version="1.0")


@server.tool()
def NAME_summary(hours: float = 12) -> str:
    """What the tool returns, in one sentence (the agent reads this)."""
    try:
        ...                                # read files, count, format: plain text; "no data" is a text, not an error
        return "..."
    except Exception as e:                 # the forge must see why it failed: return the error as text
        import traceback
        return "ERRORE: " + "".join(traceback.format_exception(e))[-1500:]


if __name__ == "__main__":
    server.run("stdio")
'''
SYS_LOOK = ("You are Aurora's forge. A capability is missing; before writing a plugin you may look at the data it needs. "
            "Reply ONLY with a JSON list of at most 3 paths relative to Aurora's folder (files or folders) to look at, "
            "e.g. [\"sys/logs/firewall\", \"sys/status/incidents.json\"]. Use the DATA PLACES given.")
SYS_WRITE = ("You are Aurora's forge: you write a small MCP plugin, in Python, that gives Aurora the missing capability. "
             "Rules: read only (it never writes files, never changes anything, never contacts the network unless the "
             "capability is impossible without it); standard library, httpx and aurora.sys_config only; tools return "
             "plain text in Italian, short, never raise for 'no data'; wrap each tool body in try/except returning "
             "'ERRORE: ' and the traceback (as in the template); timestamps like 2026-10-01T23:42:53.023+02:00 parse with "
             "datetime.fromisoformat; no secrets in the code. Aurora's logs: one folder per component under sys/logs, the "
             "live <name>.log and rotated copies <name>.<time>.log.gz (read them too when the window reaches back); a "
             "line's level is the word right after its timestamp (DEBUG, INFO, WARNING, ERROR, CRITICAL), or the JSON "
             "field \"level\" (Caddy: \"warn\", \"error\", time in the field \"ts\" in seconds) — never a word inside the "
             "message. Reply with exactly two "
             "fenced blocks: ```json with plugin.json and ```python with server.py. plugin.json: {\"name\", \"version\": "
             "\"1.0\", \"kind\": \"tool\", \"description\": {\"en\", \"it\"}, \"command\": [\"{python}\", \"server.py\"], "
             "\"env\": [], \"requires\": [], \"effects\": {\"*\": \"read\"}, \"sandbox\": {\"network\": false}, \"tests\": "
             "[{\"tool\": \"<a tool name>\", \"args\": {...}}]} — set \"network\": true only if the data is on the "
             "internet. The tests run inside the cage on the real data and must return text.\n\nTEMPLATE:\n" + TEMPLATE)


def _dir(cfg: sys_config.Config) -> Path:
    d = cfg.path("AURORA_STATUS_DIR") / "forge"
    (d / "stage").mkdir(parents=True, exist_ok=True)
    return d


def requests(cfg: sys_config.Config) -> list[dict]:
    try:
        return json.loads((_dir(cfg) / "requests.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _save(cfg: sys_config.Config, items: list[dict]) -> None:
    f = _dir(cfg) / "requests.json"
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(f)


def update(cfg: sys_config.Config, rid: str, **fields) -> dict:
    items = requests(cfg)
    item = next(i for i in items if i["id"] == rid)
    item.update(fields)
    _save(cfg, items)
    return item


def request(cfg: sys_config.Config, need: str, why: str, run_id: str | None, routine: str | None = None) -> dict:
    """Queue a missing capability once: the same need asked again joins the open request."""
    need = need.strip()[:500]
    items = requests(cfg)
    same = next((i for i in items if i["need"].lower() == need.lower() and i["status"] in ("pending", "building", "proposed")), None)
    if same:
        return same
    item = {"id": uuid.uuid4().hex[:10], "need": need, "why": why.strip()[:1000], "run_id": run_id, "routine": routine,
            "status": "pending", "created": time.time(), "attempts": 0, "plugin": None, "log": []}
    items.append(item)
    _save(cfg, items)
    return item


GAP_HINT = re.compile(r"(?i)(nessuno strumento|non ho (uno |gli |lo )?strument|non ho accesso|non posso (leggere|accedere|vedere|"
                      r"consultare|recuperare)|non dispongo|non (è|e') disponibile|non ho modo|non esiste (un|uno|alcun) "
                      r"(plugin|strumento)|no tool|cannot (read|access)|not available|unknown tool)")
SYS_GAP = ("An agent worked on a goal for Aurora and wrote a report. Did it fail, fully or in part, because Aurora has no "
           "tool to read some data or to reach some service? If yes, reply with ONE line: the missing capability, precise "
           "(what data, from where, what it should return). If it failed for another reason (an error, the network, a "
           "permission, a service not configured, nothing new to report) or did not fail, reply NONE.")


def detect_gap(llm, goal: str, report: str, requested: bool) -> str | None:
    """By code after every agent run (routines, chat, services): a report that says a tool is missing becomes a forge
    request even when the agent did not ask. A cheap textual filter decides when the reasoner is asked at all."""
    if requested or not GAP_HINT.search(report or ""):
        return None
    out = llm.complete(SYS_GAP, f"GOAL: {goal[:1500]}\n\nREPORT: {report[:3000]}", 120).answer.strip()
    return None if out.upper().startswith("NONE") or len(out) < 15 else out.splitlines()[0][:500]


class Masker:
    """What may leave for the cloud reasoner, with the owner's consent: the same text with addresses, e-mails, tokens and
    the owner's own words replaced. An address keeps the same stand-in everywhere, so formats and counts stay coherent."""

    def __init__(self, cfg: sys_config.Config):
        self.ips: dict[str, str] = {}
        own = [str(cfg.values.get(k) or "") for k in ("AURORA_OWNER_NAME", "AURORA_DOMAIN", "AURORA_WEATHER_PLACE",
                                                       "AURORA_WEATHER_LAT", "AURORA_WEATHER_LON")]
        dom = str(cfg.values.get("AURORA_DOMAIN") or "")
        if dom.count(".") >= 1:                          # aurora.example.com -> also example.com
            own.append(".".join(dom.split(".")[-2:]))
        self.own = sorted({w for w in own if len(w) >= 4 and w not in ("localhost",)}, key=len, reverse=True)
        self.user = Path.home().name

    def _ip(self, m: re.Match) -> str:
        return self.ips.setdefault(m.group(0), f"198.51.100.{len(self.ips) % 250 + 1}")

    SENSITIVE = re.compile(r'\b(\w*(?:serial|user|name|host|mac|email|domain|url|account|login)\w*)=("[^"]*"|\S+)', re.I)

    def __call__(self, text: str) -> str:
        # e-mails first: replacing the owner's domain before would leave "name@<private>" (the name leaks)
        text = re.sub(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", "user@example.org", text)
        text = self.SENSITIVE.sub(lambda m: f'{m.group(1)}="<masked>"', text)   # key=value logs: who and which device
        for w in self.own:
            text = text.replace(w, "<private>")
        text = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", self._ip, text)
        text = re.sub(r"\b[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}\b", "00:00:5e:00:53:01", text)
        text = re.sub(r"\b[0-9a-fA-F]{24,}\b|\b[A-Za-z0-9_\-]{32,}\b", "<token>", text)
        return text.replace(f"/home/{self.user}/", "/home/user/") if self.user else text


def next_pending(cfg: sys_config.Config) -> dict | None:
    if any(i["status"] == "building" and time.time() - i.get("started", 0) < 1800 for i in requests(cfg)):
        return None                                          # one build at a time
    return next((i for i in requests(cfg) if i["status"] == "pending"), None)


# ---- checks (pure: tested offline) -----------------------------------------------------------------------

def parse_reply(text: str) -> tuple[dict, str]:
    j = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S)
    p = re.search(r"```python\s*(.*?)```", text, re.S)
    if not j or not p:
        raise ValueError("the reply needs a ```json block (plugin.json) and a ```python block (server.py)")
    return json.loads(j.group(1)), p.group(1).strip() + "\n"


def check(manifest: dict, code: str, existing: set[str]) -> list[str]:
    """What is wrong with a forged plugin (empty: fine)."""
    from . import sys_ethics
    errs = []
    name = str(manifest.get("name", ""))
    if not NAME.match(name):
        errs.append("name: lowercase letters, digits, _ (3-31), starting with a letter")
    elif name in existing:
        errs.append(f"a plugin named {name} exists already: choose another name")
    if manifest.get("command") != ["{python}", "server.py"]:
        errs.append('command must be ["{python}", "server.py"]')
    if not manifest.get("tests"):
        errs.append("tests: at least one {tool, args}")
    if manifest.get("requires"):
        errs.append("requires must be empty (a forged plugin uses no secret)")
    if bad := sys_ethics.forbidden_capabilities(manifest):
        errs.append(f"refused by the ethics code (level A): {', '.join(bad)}")
    try:
        compile(code, "server.py", "exec")
    except SyntaxError as e:
        errs.append(f"server.py does not compile: {e}")
    if "server.run(" not in code:
        errs.append('server.py must end with server.run("stdio")')
    return errs


def read_only(manifest: dict) -> bool:
    """Installable without the owner: every effect read, nothing writable, no network (all enforced by the cage)."""
    sb = manifest.get("sandbox") or {}
    effects = manifest.get("effects") or {}
    return bool(effects) and all(v == "read" for v in effects.values()) and not sb.get("write") and sb.get("network") is False


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


# ---- build ---------------------------------------------------------------------------------------------

def build(cfg: sys_config.Config, llm, host, req: dict, emit, masker=None, judge=None) -> dict:
    """Write, check and test the plugin (up to 3 attempts); returns {"ok", "manifest", "stage", "errors"}."""
    log = sys_log.get_logger("forge")
    existing = {p.name for p in host.plugins(with_tools=False)}
    tools = "\n".join(f"- {p.name}: {(p.manifest.get('description') or {}).get('en', '')[:160]}"
                      for p in host.plugins(with_tools=False))
    ask = f"MISSING CAPABILITY: {req['need']}\nWHY: {req['why']}\n\nDATA PLACES:\n{data_places(cfg)}"
    raw = llm.complete(SYS_LOOK, ask, 200).answer
    m = re.search(r"\[.*\]", raw, re.S)
    try:
        looked = json.loads(m.group(0)) if m else []
    except ValueError:
        looked = []
    hours = window_hours(req["need"])                    # the counts the judge checks are for the need's window
    seen = peek(cfg, [str(x) for x in looked if isinstance(x, str)], hours or 24)
    if masker:                                           # the cloud sees the data only masked
        seen = masker(seen)
    emit("forge.look", {"paths": looked[:3], "masked": bool(masker)})
    errors: list[str] = []
    for attempt in range(1, 4):
        prompt = (f"{ask}\n\nPLUGINS ALREADY THERE (do not duplicate):\n{tools}\n\nWHAT THE DATA LOOKS LIKE:\n{seen}"
                  + (f"\n\nYOUR LAST ATTEMPT FAILED:\n" + "\n".join(errors) if errors else ""))
        reply = llm.complete(SYS_WRITE, prompt, 3500).answer
        try:
            manifest, code = parse_reply(reply)
        except ValueError as e:
            errors = [str(e)]
            emit("forge.attempt", {"attempt": attempt, "ok": False, "errors": errors})
            continue
        manifest.setdefault("sandbox", {}).setdefault("network", False)
        manifest["forged"] = {"request": req["id"], "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "need": req["need"][:200]}
        errors = check(manifest, code, existing)
        stage = _dir(cfg) / "stage" / str(manifest.get("name", "x"))
        if not errors:
            if stage.exists():
                shutil.rmtree(stage)
            stage.mkdir(parents=True)
            (stage / "plugin.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            (stage / "server.py").write_text(code, encoding="utf-8")
            # A23: the judge's facts counted now, when the plugin runs — the logs grow while the forge works (its own
            # cage runs write to the plugins' log), and an earlier count made a right output look wrong
            now_seen = peek(cfg, [str(x) for x in looked if isinstance(x, str)], hours or 24)
            errors = test(host, manifest, stage, judge or llm, masker(now_seen) if masker else now_seen, masker,
                          need=req["need"], hours=hours)
        emit("forge.attempt", {"attempt": attempt, "ok": not errors, "errors": errors[:5], "name": manifest.get("name")})
        log.info("forge %s attempt %d: %s", req["id"], attempt, "ok" if not errors else "; ".join(errors)[:300])
        if not errors:
            return {"ok": True, "manifest": manifest, "stage": str(stage), "errors": [], "attempts": attempt}
    return {"ok": False, "manifest": None, "stage": None, "errors": errors, "attempts": 3}


SYS_JUDGE = ("You check a tool a forge just wrote for a NEED. The SAMPLE shows the real data it reads: for logs, one "
             "line of each kind with how many lines of that kind exist in the NEED's time window and in all (counted by "
             "code over the live log and its rotated copies: facts). When the NEED asks for a time window, the output must "
             "count that window only: a total that matches 'in all' while the window's count differs, or that ignores the "
             "window, is WRONG (A20). The OUTPUT "
             "is what the tool returned. A folder listing in the sample is cut (at most 25 entries) and files may have been added "
             "since: more files than listed is not a contradiction. Reply WRONG: <reason> when the output contradicts the "
             "sample or its counts: it "
             "says nothing (or zero) although lines exist in the period; a total or a group is far from the counted lines "
             "of its kind (more than 10% off, or larger than all the lines); a kind of line with many lines in the period "
             "is missing from the output; it describes fields or a format the sample does not have. Otherwise reply OK. "
             "Reply with OK or WRONG: <reason> only.")


def test(host, manifest: dict, stage: Path, llm=None, sample: str = "", masker=None, need: str = "",
         hours: float | None = None) -> list[str]:
    """Run the manifest's tests in the cage, from the stage folder: every call must work and say something, and
    (with a sample of the data) a judge must find the output true to it: "no data" on data is a failure (M53)."""
    from .plg_host import Plugin
    p = Plugin(manifest["name"], stage, manifest)
    errs = []

    async def tools(session):
        return await session.list_tools()
    try:
        listed = {t.name for t in host._run(host._session(p, tools)).tools}
    except Exception as e:                                   # noqa: BLE001 - reported to the next attempt
        err = host.cfg.path("AURORA_LOG_DIR") / "plugins" / f"{p.name}.stderr.log"
        tail = err.read_text(errors="replace")[-1200:] if err.exists() else ""   # why: the plugin's own traceback
        return [f"the plugin does not start in the cage: {type(e).__name__}: {str(e)[:300]}"
                + (f"\nITS ERROR OUTPUT (last lines):\n{tail}" if tail.strip() else "")]
    for t in manifest.get("tests", [])[:5]:
        name, args = t.get("tool"), t.get("args") or {}
        if name not in listed:
            errs.append(f"test calls {name}, the plugin has {sorted(listed)}")
            continue

        async def call(session, name=name, args=args):
            return await session.call_tool(name, args)
        try:
            res = host._run(host._session(p, call))
            text = "\n".join(c.text for c in getattr(res, "content", []) if getattr(c, "type", "") == "text")
            if getattr(res, "is_error", False) or not text.strip() or text.lstrip().startswith("ERRORE:"):
                errs.append(f"{name}({args}) failed or returned nothing: {text[:400]}")
            elif llm is not None and sample:
                shown = masker(text) if masker else text
                window = f"window: {hours:g} h" if hours else "no time window asked: judge the whole data"
                verdict = llm.complete(SYS_JUDGE, f"NEED: {need} ({window})\n\nSAMPLE:\n{sample[:6000]}\n\n"
                                                  f"TOOL {name}({args}) OUTPUT:\n{shown[:3000]}", 120).answer.strip()
                if not verdict.upper().startswith("OK"):
                    errs.append(f"{name}({args}) returned \"{text[:300]}\", judged {verdict[:300]}")
        except Exception as e:                               # noqa: BLE001
            errs.append(f"{name}({args}): {type(e).__name__}: {str(e)[:400]}")
    return errs


def install(cfg: sys_config.Config, stage: str) -> Path:
    """The tested plugin goes live: its folder is copied into the plugins directory (never over an existing one)."""
    src = Path(stage)
    dest = cfg.path("AURORA_PLUGINS_DIR") / src.name
    if dest.exists():
        raise FileExistsError(f"plugin {src.name} exists already")
    shutil.copytree(src, dest)
    icon = cfg.path("AURORA_PLUGINS_DIR") / "self" / "icon.png"
    if icon.exists() and not (dest / "icon.png").exists():
        shutil.copy(icon, dest / "icon.png")
    return dest
