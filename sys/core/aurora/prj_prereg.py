# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔒 Frozen predictions in a project (ROADMAP N142; owner: «dare ad Aurora, negli agenti dei progetti, le previsioni
congelate e il revisore severo»; decided: «avviso» mode by default).

Before an experiment whose result will be reported, the agent writes down what it expects — numbered predictions —
and the code that will test them; Aurora freezes both: the predictions in `prereg/NNN_<slug>.md`, and in an
append-only ledger `prereg/LEDGER.jsonl` the SHA-256 of that file and of each code file. After the experiment the
agent closes the entry with an outcome per prediction (passed / failed / void, its value, a note) and the evidence;
Aurora hashes everything again: if a file changed after the freeze the entry is marked «changed after freeze» and its
«passed» outcomes are not counted. Nothing under prereg/ is written by a write or edit tool (refused here, in prj_act
and in prj_policy.guard for the agent's plugin); a shell write in the cage is caught by the hashes. The ledger's
lines are also kept in the user's state, outside the project (the cage cannot reach it): that copy is the truth, the
project's file the readable one, and a difference is said.

A prediction whose text starts with «PROOF:» and a .lean file of the project (N143) is closed by Aurora only: at the
close the agent's outcome for it is ignored and prj_proof checks the file with Lean (passed iff proved, void when the
check could not run); the check is recorded in the ledger. The file, when it exists at the freeze, is hashed with the
code: a statement weakened after the freeze is «changed after freeze».

AURORA_PREREG_MODE: off (no rule, no tools offered to the agent), warn (default: the rule in the drafts, a phase that
ran commands without freezing anything is said in the reply), strict (warn, and a command in the project is refused
until something was frozen in the same run).
"""
from __future__ import annotations

import hashlib
import json
import posixpath
import re
import time
from pathlib import Path

from . import prj_run, sys_config
from . import sys_users_layout as L

DIR = "prereg"
LEDGER = "LEDGER.jsonl"
LOCKED = (DIR, "reviews", "discover", "longrun", "novelty")   # written by Aurora only: frozen predictions, reviews (N142),
# discovery reports (N147), long runs' reports (N145), literature checks (N146)
OUTCOMES = ("passed", "failed", "void")
PROOF = "PROOF:"                # a prediction closed by Aurora's Lean check (prj_proof, N143)
MAX_PREDICTIONS = 50
# C624: titles and entries that only Aurora's engines write (the discovery engine, N147): an agent's freeze with such a
# title is refused, and an entry with an «origin» is closed by its engine only
RESERVED = ("Discovery split", "Discovered law", "Long run")   # the discovery engine's (N147), the long runs' (N145)


# C653: letters of other scripts that look like Latin ones («Disсovered» with a Cyrillic «с» passed), mapped to them
_LOOKALIKE = str.maketrans({**dict(zip("аеорсухіјѕԁӏкмнтвгпилАЕОРСУХІЈЅКМНТВ", "aeopcyxijsdlkmhtbrnuiAEOPCYXIJSKMHTB")),
                            **dict(zip("αοριυνκτεχΑΒΕΗΙΚΜΝΟΡΤΥΧΖ", "aopiuvktexABEHIKMNOPTYXZ")),
                            "ı": "i", "ℓ": "l", "ꓲ": "l", "ǀ": "l", "Ɩ": "l", "ɑ": "a", "ɡ": "g", "ο": "o"})


def skeleton(title: str) -> str:
    """The title as it reads: NFKC, format characters (Cf) dropped, accents dropped, lookalike letters of other scripts
    mapped to Latin ones, case-folded, spaces squeezed."""
    import unicodedata
    t = unicodedata.normalize("NFKC", str(title or ""))
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Cf").translate(_LOOKALIKE)
    t = "".join(ch for ch in unicodedata.normalize("NFKD", t) if not unicodedata.combining(ch))
    return " ".join(t.split()).casefold()


def letters(text: str) -> str:
    """The skeleton's letters and digits only (C666: «Long-run», «Discovered_law» passed), a letter of another script
    that no table maps kept as «?» (C666: an Armenian «օ» in «Lօng run» passed)."""
    return "".join(c if c.isascii() else "?" for c in skeleton(text) if c.isalnum())


def reserved(title: str) -> bool:
    """A title only Aurora's engines may use, however it is written (C633: an invisible character before «Discovered»
    passed; C653: a lookalike letter of another script; C666: a separator, or a letter no table maps): its letters
    compared with the reserved ones, a «?» matching any letter. The engines' own entries carry «origin» besides."""
    got = letters(title)
    for r in RESERVED:
        want = letters(r)
        if len(got) >= len(want) and all(g in ("?", w) for g, w in zip(got, want)):
            return True
    return False

RULE = ("Frozen predictions (Aurora's rule): before running any experiment whose result you will report, freeze its "
        "predictions with freeze_predictions (numbered, measurable, with the code files that test them); close them "
        "afterwards with close_predictions (each passed / failed / void, with the measured value); report every "
        "failed prediction. Files under prereg/ cannot be written: Aurora keeps them.")

_ITEMS = {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "string"}, "text": {"type": "string"}},
                                     "required": ["id", "text"]}}
_OUTS = {"type": "array", "items": {"type": "object", "properties": {
    "id": {"type": "string"}, "outcome": {"type": "string", "enum": list(OUTCOMES)}, "value": {"type": "string"},
    "note": {"type": "string"}}, "required": ["id", "outcome"]}}
TOOLS = [
    {"name": "freeze_predictions", "description": "Freeze the predictions of an experiment BEFORE running it: "
     "numbered measurable predictions and the code files that will test them (paths in the project). Aurora writes "
     "prereg/NNN_<slug>.md and hashes it and the code; returns the entry's id.",
     "inputSchema": {"type": "object", "properties": {"title": {"type": "string"}, "predictions": _ITEMS,
                                                      "code_files": {"type": "array", "items": {"type": "string"}}},
                     "required": ["title", "predictions", "code_files"]}},
    {"name": "close_predictions", "description": "Close a frozen entry after the experiment: one outcome per "
     "prediction (passed / failed / void, the measured value, a note) and the evidence (a file of the project). "
     "Aurora checks the hashes again: a file changed after the freeze is said, and its «passed» do not count.",
     "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}, "outcomes": _OUTS,
                                                      "evidence": {"type": "string"}},
                     "required": ["id", "outcomes", "evidence"]}},
    {"name": "predictions_ledger", "description": "The project's frozen predictions: a short table (open / closed, "
     "passed / failed / void, integrity).", "inputSchema": {"type": "object", "properties": {}}},
]
NAMES = {t["name"] for t in TOOLS}


def mode(cfg: sys_config.Config) -> str:
    m = str(cfg["AURORA_PREREG_MODE"] or "warn").strip().lower()
    return m if m in ("off", "warn", "strict") else "warn"


def rule(cfg: sys_config.Config) -> str:
    """The rule for a draft or the conductor's prompt; empty when the mode is off."""
    return "" if mode(cfg) == "off" else RULE


def locked(rel: str) -> bool:
    """A path (relative to the project) that no write or edit tool may touch: under prereg/, reviews/ or discover/."""
    parts = posixpath.normpath(str(rel or "").replace("\\", "/").lstrip("/")).split("/")
    return bool(parts) and parts[0] in LOCKED


def refusal(rel: str) -> str:
    return (f"REFUSED: {rel} is under {'/ or '.join(LOCKED)}/ — frozen predictions, reviews and discovery reports are "
            "written by Aurora only (immutable). Use freeze_predictions / close_predictions.")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _sha_in(root: Path, rel: str) -> str:
    """A project file's SHA-256, opened from the project's folder, no link followed, a regular file only (C665: a FIFO
    swapped in by a long run hung the lock held around a freeze)."""
    from . import prj_safeio
    return prj_safeio.sha_in(root, rel)


def _is_file(root: Path, rel: str) -> bool:
    from . import prj_safeio
    try:
        return prj_safeio.is_file(root, rel)
    except ValueError:
        return False


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _shadow(cfg: sys_config.Config, project: str) -> Path:
    return L.place(cfg, "state", cfg.user) / "projects" / project / "prereg.jsonl"


def _lines(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    out = []
    for line in text.splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _append(cfg: sys_config.Config, root: Path, project: str, e: dict) -> None:
    line = json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n"
    (root / DIR).mkdir(exist_ok=True)
    s = _shadow(cfg, project)
    s.parent.mkdir(parents=True, exist_ok=True)
    with s.open("a", encoding="utf-8") as fh:              # the truth first (outside the cage)
        fh.write(line)
    from . import prj_safeio                                 # then the project's copy, no link followed (C665)
    prj_safeio.write_bytes(root, f"{DIR}/{LEDGER}", line.encode("utf-8"), append=True)


def entries(cfg: sys_config.Config, project: str, since: float | None = None) -> list[dict]:
    """Each entry's state (the freeze, then its close folded in), from Aurora's own copy of the ledger; `since` (a
    time): only the entries frozen from then on (a phase's)."""
    by: dict[str, dict] = {}
    for e in _lines(_shadow(cfg, project)):
        if e.get("event") == "freeze":
            by[e["id"]] = dict(e)
        elif e.get("event") == "close" and e.get("id") in by:
            by[e["id"]].update({k: v for k, v in e.items() if k != "event"})
    out = list(by.values())
    return [e for e in out if since is None or float(e.get("t", 0)) >= since]


def ledger_intact(cfg: sys_config.Config, project: str) -> bool:
    """The project's LEDGER.jsonl says what Aurora's own copy says (a shell in the cage could have rewritten it)."""
    root = prj_run.project_dir(cfg, project)
    return _lines(_shadow(cfg, project)) == _lines(root / DIR / LEDGER)


def _rel_file(root: Path, rel: str) -> tuple[str, Path]:
    """The path as the project sees it, checked lexically (C665: never resolved first and opened by name later)."""
    from . import prj_safeio
    try:
        r = prj_safeio.norm(str(rel or "").strip(), root)
    except ValueError:
        raise ValueError(f"{rel}: outside the project") from None
    if r == ".":
        raise ValueError(f"{rel}: outside the project")
    if ".git" in r.split("/") or locked(r):
        raise ValueError(f"{rel}: not a code file of the project")
    if not _is_file(root, r):
        raise ValueError(f"{rel}: no such file in the project")
    return r, root / r


def _proof_target(root: Path, text: str) -> str:
    """«PROOF: <file.lean> …» → the file's path in the project; ValueError when it is not a .lean file inside it."""
    words = text[len(PROOF):].split()
    p = (root / (words[0] if words else "")).resolve()
    if not words or p == root or not p.is_relative_to(root) or p.suffix != ".lean" or locked(p.relative_to(root).as_posix()):
        raise ValueError(f"«{PROOF} <file.lean>» needs a .lean file of the project ({text[:80]})")
    return p.relative_to(root).as_posix()


def _slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40].strip("-")
    return s or "predictions"


def freeze(cfg: sys_config.Config, project: str, title: str, predictions: list, code_files: list,
           origin: str = "") -> dict:
    """The predictions written and hashed with their code; ValueError (said as REFUSED) for a bad request. `origin`:
    the engine that froze it (only Aurora's own code passes one; such an entry is closed by that engine only)."""
    root = prj_run.project_dir(cfg, project).resolve()
    title = " ".join(str(title or "").split())[:160]
    if not title:
        raise ValueError("a title")
    preds = [{"id": str((x or {}).get("id", "")).strip(), "text": str((x or {}).get("text", "")).strip()}
             for x in (predictions or []) if isinstance(x, dict)]
    if not preds or len(preds) > MAX_PREDICTIONS or any(not x["id"] or not x["text"] for x in preds):
        raise ValueError(f"1 to {MAX_PREDICTIONS} predictions, each with an id and a text")
    ids = [x["id"] for x in preds]
    if len(set(ids)) != len(ids):
        raise ValueError(f"duplicate prediction ids: {', '.join(sorted({i for i in ids if ids.count(i) > 1}))}")
    code = {}
    for rel in code_files or []:
        r, _ = _rel_file(root, str(rel))
        code[r] = _sha_in(root, r)
    proofs = {x["id"]: _proof_target(root, x["text"]) for x in preds if x["text"].startswith(PROOF)}
    for rel in proofs.values():                             # the statement frozen too, when it is written already
        if _is_file(root, rel):
            code.setdefault(rel, _sha_in(root, rel))
    n = len(entries(cfg, project)) + 1
    eid = f"{n:03d}"
    rel = f"{DIR}/{eid}_{_slug(title)}.md"
    text = [f"# Frozen predictions {eid} — {title}", "", f"Frozen (UTC): {_now()}", "", "## Predictions", ""]
    text += [f"{i}. **{x['id']}** — {x['text']}" for i, x in enumerate(preds, 1)]
    if proofs:
        text += ["", f"Predictions «{PROOF}» are closed by Aurora's Lean check (proof_check), never by the agent."]
    text += ["", "## Code files (SHA-256 at the freeze)", ""]
    text += [f"- `{k}` — {v}" for k, v in code.items()] or ["- (none listed: only the predictions are frozen)"]
    from . import prj_safeio                                 # C665: created exclusively, never through a link
    blob = ("\n".join(text) + "\n").encode("utf-8")
    rel = prj_safeio.write_new(root, rel, blob)             # a name taken: the next free one (never overwritten)
    e = {"event": "freeze", "id": eid, "title": title, "created": _now(), "t": time.time(), "file": rel,
         "sha256": hashlib.sha256(blob).hexdigest(), "code": code, "predictions": ids, "status": "open", **({"proofs": proofs} if proofs else {}),
         **({"origin": str(origin)} if origin else {})}
    _append(cfg, root, project, e)
    return e


def close(cfg: sys_config.Config, project: str, eid: str, outcomes: list, evidence: str) -> dict:
    """The outcomes recorded, everything hashed again; a changed file → «changed after freeze», «passed» not counted."""
    root = prj_run.project_dir(cfg, project).resolve()
    e = next((x for x in entries(cfg, project) if x["id"] == str(eid).strip()), None)
    if e is None:
        raise ValueError(f"no frozen entry {eid}")
    if e.get("status") != "open":
        raise ValueError(f"entry {eid} is closed already")
    outs = [{"id": str((o or {}).get("id", "")).strip(), "outcome": str((o or {}).get("outcome", "")).strip().lower(),
             "value": str((o or {}).get("value", "") or "")[:300], "note": str((o or {}).get("note", "") or "")[:500]}
            for o in (outcomes or []) if isinstance(o, dict)]
    bad = [o["id"] for o in outs if o["outcome"] not in OUTCOMES]
    if bad:
        raise ValueError(f"outcome must be passed / failed / void ({', '.join(bad)})")
    given = [o["id"] for o in outs]
    proofs = e.get("proofs") or {}
    unknown = sorted(set(given) - set(e["predictions"]))
    missing = [i for i in e["predictions"] if i not in given and i not in proofs]   # a PROOF: one is Aurora's
    if unknown or missing or len(set(given)) != len(given):
        raise ValueError("one outcome per frozen prediction" + (f"; unknown: {', '.join(unknown)}" if unknown else "")
                         + (f"; missing: {', '.join(missing)}" if missing else ""))
    if e.get("origin") and locked(str(evidence)):            # an engine's own evidence, in its locked folder (C625)
        ev = posixpath.normpath(str(evidence).replace("\\", "/").lstrip("/"))
        if not _is_file(root, ev):
            raise ValueError(f"{evidence}: no such file in the project")
    else:
        ev, _ = _rel_file(root, evidence)
    changed = []
    for rel, h in [(e["file"], e["sha256"]), *e["code"].items()]:
        try:
            same = _sha_in(root, rel) == h
        except (ValueError, OSError):
            same = False
        if not same:
            changed.append(rel)
    intact = not changed
    checks = {}
    if proofs:                                              # N143: Aurora's own check, the agent's outcome ignored
        from . import prj_proof
        by = {o["id"]: o for o in outs}
        for pid, rel in proofs.items():
            r = prj_proof.check(cfg, project, rel)
            claimed = (by.get(pid) or {}).get("outcome", "")
            why = "; ".join(r["errors"][:2])
            by[pid] = {"id": pid, "outcome": {"proved": "passed", "error": "void"}.get(r["status"], "failed"),
                       "value": r["status"], "claimed": claimed,
                       "note": (f"closed by Aurora's Lean check (proof_check){'; the agent said ' + claimed if claimed else ''}"
                                + (f": {why}" if why else ""))[:500]}
            checks[pid] = {**{k: r.get(k) for k in ("path", "status", "seconds", "sha256", "axioms", "theorems")},
                           "errors": r["errors"][:5]}
        outs = [by[i] for i in e["predictions"] if i in by]
    count = {k: sum(o["outcome"] == k for o in outs) for k in OUTCOMES}
    counted = dict(count) if intact else {"passed": 0, "failed": count["failed"], "void": count["void"],
                                          "not_counted": count["passed"]}
    c = {"event": "close", "id": e["id"], "outcomes": outs, "evidence": ev, "closed": _now(), "status": "closed",
         "integrity": "intact" if intact else "changed after freeze", "changed": changed, "counted": counted,
         **({"proofs": checks} if checks else {})}
    _append(cfg, root, project, c)
    return {**e, **{k: v for k, v in c.items() if k != "event"}}


def table(cfg: sys_config.Config, project: str, since: float | None = None) -> str:
    rows = entries(cfg, project, since)
    if not rows:
        return "(no frozen predictions)"
    out = ["| id | title | status | passed | failed | void | integrity |", "|---|---|---|---|---|---|---|"]
    for e in rows:
        c = e.get("counted") or {}
        p = c.get("passed", "")
        if c.get("not_counted"):
            p = f"0 ({c['not_counted']} not counted)"
        out.append(f"| {e['id']} | {e['title'][:60]} | {e['status']} | {p} | {c.get('failed', '')} | "
                   f"{c.get('void', '')} | {e.get('integrity', '—')} |")
    if not ledger_intact(cfg, project):
        out.append("\n⚠️ prereg/LEDGER.jsonl in the project differs from Aurora's own copy: it was changed by hand")
    return "\n".join(out)


def balance(cfg: sys_config.Config, project: str, since: float | None = None) -> str:
    """One line for the conductor's reply, from the ledger Aurora keeps (never from the agent's report)."""
    rows = entries(cfg, project, since)
    if not rows:
        return "frozen predictions (prereg/, read by Aurora): none" + (" in this phase" if since is not None else "")
    parts = []
    for e in rows:
        if e["status"] == "open":
            parts.append(f"{e['id']} open")
            continue
        c = e.get("counted") or {}
        parts.append(f"{e['id']} closed {e.get('integrity')}: {c.get('passed', 0)} passed, {c.get('failed', 0)} failed, "
                     f"{c.get('void', 0)} void" + (f", {c['not_counted']} passed NOT counted" if c.get("not_counted") else ""))
    tail = "" if ledger_intact(cfg, project) else "; the project's LEDGER.jsonl was changed by hand"
    return "frozen predictions (prereg/, read by Aurora): " + "; ".join(parts) + tail


def missing_note(cfg: sys_config.Config, project: str, commands: int, since: float, lang: str = "it") -> str:
    """A phase that ran commands but froze nothing (warn and strict): said plainly, by Aurora; '' otherwise."""
    if mode(cfg) == "off" or commands <= 0 or entries(cfg, project, since):
        return ""
    if str(lang).startswith("en"):
        return (f"⚠️ **Doesn't hold**: the phase ran {commands} commands but no prediction was frozen: its results "
                "were not predicted before they were seen.")
    return (f"⚠️ **Non regge**: la fase ha eseguito {commands} comandi ma nessuna previsione congelata: i risultati non "
            "erano stati previsti prima di vederli.")


# ---- the tools: the conductor's (prj_act, the run's project) and the agent's (agt_loop, «project» given) ----------
def tool(cfg: sys_config.Config, project: str, name: str, a: dict, done: set | None = None) -> str:
    """A tool call → its text; a refusal says why. `done`: the projects frozen in this run (strict mode)."""
    try:
        if name == "freeze_predictions":
            title = " ".join(str(a.get("title", "")).split())
            if reserved(title):
                raise ValueError(f"titles starting with {' / '.join(RESERVED)} are Aurora's engines' (discover_law, "
                                 "long_run)")
            e = freeze(cfg, project, title, a.get("predictions") or [], a.get("code_files") or [])
            if done is not None:
                done.add(project)
            return (f"FROZEN {e['id']}: {len(e['predictions'])} predictions, {len(e['code'])} code files hashed "
                    f"({e['file']}). Run the experiment now; then close_predictions(id=\"{e['id']}\", …).")
        if name == "close_predictions":
            mine = next((x for x in entries(cfg, project) if x["id"] == str(a.get("id", "")).strip()), None)
            if mine and mine.get("origin"):
                raise ValueError(f"entry {mine['id']} is closed by Aurora's {mine['origin']} engine, never by hand")
            e = close(cfg, project, str(a.get("id", "")), a.get("outcomes") or [], str(a.get("evidence", "")))
            failed = [o for o in e["outcomes"] if o["outcome"] == "failed"]
            out = f"CLOSED {e['id']}: integrity {e['integrity']}; counted {e['counted']}."
            if e["changed"]:
                out += (f"\nWARNING: changed after freeze: {', '.join(e['changed'])} — the «passed» outcomes of "
                        f"{e['id']} do not count. Say so in your report.")
            if e.get("proofs"):
                said = {o["id"]: o.get("claimed") for o in e["outcomes"]}
                out += "\nPROOF predictions, closed by Aurora's Lean check (your outcome ignored): " + "; ".join(
                    f"{i} {c['status']}" + (f" (you said {said[i]})" if said.get(i) else "")
                    for i, c in e["proofs"].items())
            if failed:
                out += "\nReport these failed predictions: " + "; ".join(f"{o['id']} ({o['value'] or 'no value'})"
                                                                      for o in failed)
            return out
        if name == "predictions_ledger":
            return table(cfg, project)
    except ValueError as e:
        return f"REFUSED: {e}"
    raise ValueError(f"no tool {name}")


def offered(cfg: sys_config.Config, text: str) -> list[dict]:
    """The tools in the agent's form («project» added), offered when the mode is on and its goal or context carries
    the rule (a project's phase): no other run pays for them."""
    if mode(cfg) == "off" or "freeze_predictions" not in (text or ""):
        return []
    out = []
    for t in TOOLS:
        s = json.loads(json.dumps(t["inputSchema"]))
        s["properties"] = {"project": {"type": "string", "description": "the project's name"}, **s["properties"]}
        s["required"] = ["project", *s.get("required", [])]
        out.append({"name": t["name"], "description": t["description"], "input_schema": s})
    return out


def agent_call(agent, name: str, a: dict) -> str:
    project = str(a.get("project") or a.get("name") or "")
    if not project:
        return f"ERROR: {name} needs «project» (the project's name)."
    try:
        frozen = agent.__dict__.setdefault("prereg_frozen", set())
        out = tool(agent.cfg, project, name, a, frozen)
    except (ValueError, OSError) as e:
        return f"ERROR: {e}"
    if isinstance(getattr(agent, "projects", None), set):
        agent.projects.add(project)                          # the run's report stays with the project
    return out


def strict_refusal(cfg: sys_config.Config, project: str, frozen: set | None) -> str:
    """strict: a command in the project waits until something was frozen in this run; '' to go on."""
    if mode(cfg) != "strict" or project in (frozen or set()):
        return ""
    return ("REFUSED (AURORA_PREREG_MODE=strict): freeze the predictions of this experiment first with "
            "freeze_predictions, then run it.")
