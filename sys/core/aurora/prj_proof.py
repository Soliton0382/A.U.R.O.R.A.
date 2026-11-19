# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📐 Formal proofs in a project, checked by Lean 4 + Mathlib (ROADMAP N143; owner: «cerchiamo di capire come integrare
lean in aurora così almeno lo sa usare»; decided: Lean lives in sys/runtime/lean).

check(cfg, project, path) → {status: proved | not_proved | refused | error, errors, axioms, forbidden, seconds}:
  1. the .lean file must be inside the project (resolved: no «..», no link out, not .git);
  2. its source — and that of each project file it imports — is scanned, comments and strings left out: `sorry`,
     `admit`, `native_decide` / `decide +native`, `axiom` declarations, `unsafe`, `implemented_by`, `extern`,
     `macro` / `elab` / `syntax` / `initialize` (new tactics or attributes run meta code), `run_cmd` / `run_elab` /
     `run_tac` / `by_elab`, `#eval`, `#exit`, `set_option` on debug or kernel options, and any `import` outside
     Mathlib / Std / Lean / Batteries / Aesop / the project's own files are REFUSED before anything is compiled;
  3. it is compiled in a cage (prj_run.cage, read only: no network, no home, the project bound read only, the Lean
     home bound read only, build outputs in the cage's private tmpfs /tmp) by the workspace's own lean binary with the
     workspace's LEAN_PATH (no lake, no elan inside: nothing tries to write the toolchain), the source on stdin with
     `#print axioms` appended for each theorem / lemma it declares (line numbers unchanged);
  4. «proved» only when it compiles with no error, declares at least one theorem, and every one depends on no axiom
     outside {propext, Classical.choice, Quot.sound} (sorryAx — an elaboration error — and Lean.ofReduceBool fail it).
Time: AURORA_PROOF_TIMEOUT_S. Memory: Lean's own cap (-M MEMORY_MB); an address-space limit (ulimit -v / prlimit)
cannot be used — Lean maps Mathlib's .olean files, several GB of address space. Every check is kept in the user's
state (the last HISTORY), for the page's «Verifica formale».
"""
from __future__ import annotations

import hashlib
import json
import re
import shlex
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from . import prj_run, sys_config
from . import sys_users_layout as L

NAME = "proof_check"
STANDARD = ("propext", "Classical.choice", "Quot.sound")
ROOTS = {"Mathlib", "Std", "Lean", "Batteries", "Aesop"}
MEMORY_MB = 8192                # Lean's -M: a soft cap, checked by Lean itself while it elaborates
ERR_CHARS = 4000                # the compiler's errors kept (the start: the first error is the one that matters)
HISTORY = 50
MAX_DEPS = 30                   # project files imported (transitively)
BUILD = "/tmp/build"            # in the cage's private tmpfs

_ID = r"(?<![\w.'!?])"
_END = r"(?![\w'!?])"
FORBIDDEN = [(what, re.compile(rx, re.M)) for what, rx in (
    ("sorry", _ID + r"sorry" + _END), ("admit", _ID + r"admit" + _END),
    ("native_decide", _ID + r"native_decide" + _END), ("decide +native", r"\+\s*native" + _END + r"|native\s*:=\s*true"),
    ("ofReduceBool", r"ofReduce(?:Bool|Nat)" + _END), ("axiom", _ID + r"axiom" + _END),
    ("unsafe", _ID + r"unsafe" + _END), ("implemented_by", _ID + r"implemented_by" + _END),
    ("extern", _ID + r"extern" + _END),
    ("macro / elab / syntax", _ID + r"(?:macro_rules|macro|elab_rules|elab|syntax|declare_syntax_cat|initialize|"
                              r"builtin_initialize|register_option|register_builtin_option)" + _END),
    ("run_cmd / run_elab / run_tac / by_elab", _ID + r"(?:run_cmd|run_elab|run_meta|run_tac|by_elab)" + _END),
    ("#eval", r"#eval" + _END + "!?"), ("#exit", r"#exit" + _END),
    ("set_option (debug / kernel)", r"set_option\s+(?:debug\.\S+|\S*[kK]ernel\S*|allowUnsafeReducibility)"))]
IMPORT = re.compile(r"^\s*(?:(?:public|private|meta)\s+)*import\s+([^\n]+)$", re.M)
DECL = re.compile(r"^\s*(?:@\[[^\]]*\]\s*)*(?:(?:private|protected|noncomputable|nonrec|public)\s+)*(?:theorem|lemma)\s+"
                  r"([^\s:({\[⦃]+)")
SCOPE = re.compile(r"^\s*(?:(namespace)\s+(\S+)|(?:noncomputable\s+)?(section)\b|(end)\b)")
AXIOMS = re.compile(r"^'(.+)' (?:depends on axioms: \[(.*)\]|does not depend on any axioms)")

TOOL = {"name": NAME, "description": "Check a Lean 4 proof (a .lean file of the project, Mathlib available) with "
        "Aurora's Lean: no sorry / admit / native_decide / axiom / unsafe / custom tactics; compiled in a read-only "
        "cage; «proved» only when every theorem and lemma depends on no axiom but propext, Classical.choice and "
        "Quot.sound. Returns the status, the compiler's errors and each theorem's axioms. A theorem is claimed proved "
        "only when this says PROVED.",
        "inputSchema": {"type": "object", "properties": {"path": {"type": "string",
                                                                  "description": "the .lean file, in the project"}},
                        "required": ["path"]}}
RULE = ("Formal proofs (Aurora's rule): a theorem is claimed proved only when proof_check (Lean 4 + Mathlib, run by "
        "Aurora) says PROVED for its .lean file; a prediction whose text is «PROOF: <file.lean>» is closed by "
        "Aurora's own check, not by the outcome you give.")


def enabled(cfg: sys_config.Config) -> bool:
    return bool(cfg["AURORA_PROOF_ENABLED"])


def rule(cfg: sys_config.Config) -> str:
    return RULE if enabled(cfg) else ""


# ---- the source: comments and strings out, then the scans ------------------------------------------------------
def strip(src: str) -> str:
    """The code alone: comments (line, nested block, doc) and string / char literals blanked, newlines kept (the lines
    of what is found stay right)."""
    out, i, n = [], 0, len(src)

    def blank(a: str) -> str:
        return "".join(c if c == "\n" else " " for c in a)
    while i < n:
        c = src[i]
        if src.startswith("--", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
            out.append(blank(src[i:j]))
            i = j
        elif src.startswith("/-", i):
            depth, j = 1, i + 2
            while j < n and depth:
                if src.startswith("/-", j):
                    depth, j = depth + 1, j + 2
                elif src.startswith("-/", j):
                    depth, j = depth - 1, j + 2
                else:
                    j += 1
            out.append(blank(src[i:j]))
            i = j
        elif c == '"':
            j = i + 1
            while j < n and src[j] != '"':
                j += 2 if src[j] == "\\" else 1
            out.append(blank(src[i:j + 1]))
            i = j + 1
        elif c == "'" and (i == 0 or not (src[i - 1].isalnum() or src[i - 1] in "_'!?.")) and (
                src[i + 2:i + 3] == "'" or (src[i + 1:i + 2] == "\\" and src[i + 3:i + 4] == "'")):
            k = 3 if src[i + 2:i + 3] == "'" else 4
            out.append(" " * k)
            i += k
        else:
            out.append(c)
            i += 1
    return "".join(out)


def forbidden(code: str, rel: str) -> list[dict]:
    found = []
    for what, rx in FORBIDDEN:
        for m in rx.finditer(code):
            found.append({"what": what, "file": rel, "line": code.count("\n", 0, m.start()) + 1})
    return sorted(found, key=lambda f: (f["file"], f["line"]))


def imports(code: str) -> list[str]:
    return [m for line in IMPORT.findall(code) for m in line.split()]


def declared(code: str) -> list[str]:
    """The full names of the theorems and lemmas declared (namespaces followed; `_root_.` honoured)."""
    stack: list[str | None] = []
    names = []
    for line in code.splitlines():
        if m := SCOPE.match(line):
            if m.group(1):
                stack.append(m.group(2))
            elif m.group(3):
                stack.append(None)
            elif m.group(4) and stack:
                stack.pop()
            continue
        if m := DECL.match(line):
            n = m.group(1)
            ns = [s for s in stack if s]
            names.append(n[len("_root_."):] if n.startswith("_root_.") else ".".join([*ns, n]))
    return list(dict.fromkeys(names))


# ---- the toolchain -----------------------------------------------------------------------------------------------
def toolchain(cfg: sys_config.Config) -> dict:
    """{home, lean, lean_path} of AURORA_LEAN_HOME; RuntimeError «Lean non installato» when a piece is missing."""
    home = cfg.path("AURORA_LEAN_HOME")
    ws = home / "workspace"
    try:
        tc = (ws / "lean-toolchain").read_text(encoding="utf-8").strip()
    except OSError:
        raise RuntimeError(f"Lean non installato (no workspace in AURORA_LEAN_HOME = {cfg['AURORA_LEAN_HOME']})") from None
    tdir = home / "elan" / "toolchains" / tc.replace("/", "--").replace(":", "---")
    lean = tdir / "bin" / "lean"
    mathlib = ws / ".lake" / "packages" / "mathlib" / ".lake" / "build" / "lib" / "lean"
    if not lean.is_file():
        raise RuntimeError(f"Lean non installato (no toolchain {tc} in AURORA_LEAN_HOME)")
    if not mathlib.is_dir():
        raise RuntimeError("Lean non installato (Mathlib not built in the workspace)")
    libs = sorted(str(p) for p in (ws / ".lake" / "packages").glob("*/.lake/build/lib/lean") if p.is_dir())
    libs += [str(p) for p in (ws / ".lake" / "build" / "lib" / "lean", tdir / "lib" / "lean") if p.is_dir()]
    return {"home": home.resolve(), "lean": lean, "lean_path": ":".join([BUILD, *libs])}


def cage(cfg: sys_config.Config, project: Path, tc: dict, script: str) -> list[str]:
    """prj_run's read-only cage, the Lean home bound read only and LEAN_PATH set (both before --clearenv's end)."""
    args = prj_run.cage(cfg, project, script, readonly=True)
    at = args.index("--clearenv")
    args[at:at] = ["--ro-bind", str(tc["home"]), str(tc["home"])]
    at = args.index("--chdir")
    args[at:at] = ["--setenv", "LEAN_PATH", tc["lean_path"]]
    return args


# ---- the check ----------------------------------------------------------------------------------------------------
def _file(root: Path, rel: str) -> tuple[str, Path]:
    """The path checked lexically; the file is read from the project's folder, no link followed (C665)."""
    from . import prj_safeio
    try:
        r = prj_safeio.norm(str(rel or "").strip(), root)
    except ValueError:
        raise ValueError(f"{rel}: outside the project") from None
    if r == ".":
        raise ValueError(f"{rel}: outside the project")
    if ".git" in r.split("/"):
        raise ValueError(f"{rel}: not a file of the project")
    if not r.endswith(".lean"):
        raise ValueError(f"{rel}: not a .lean file")
    try:
        ok = prj_safeio.is_file(root, r)
    except ValueError:
        ok = False
    if not ok:
        raise ValueError(f"{rel}: no such file in the project")
    return r, root / r


def _deps(root: Path, rel: str, code: str) -> tuple[list[tuple[str, str, Path]], list[dict]]:
    """The project files imported, in build order [(module, rel, path)], and what is refused in them or their imports."""
    order: list[tuple[str, str, Path]] = []
    bad: list[dict] = []
    seen: set[str] = set()

    def visit(r: str, c: str, chain: tuple) -> None:
        for mod in imports(c):
            if mod.split(".")[0] in ROOTS:
                continue
            from . import prj_safeio
            dr = mod.replace(".", "/") + ".lean"            # C665: lexical, opened without links, a regular file
            try:
                ok = ".." not in dr.split("/") and prj_safeio.is_file(root, dr)
            except ValueError:
                ok = False
            p = root / dr
            if not ok:
                bad.append({"what": f"import {mod} (not Mathlib / Std / Lean / Batteries / Aesop nor a file of the "
                                    "project)", "file": r, "line": 0})
                continue
            if mod in chain:
                bad.append({"what": f"import {mod}: a cycle", "file": r, "line": 0})
                continue
            if mod in seen:
                continue
            if len(seen) >= MAX_DEPS:
                bad.append({"what": f"more than {MAX_DEPS} project files imported", "file": r, "line": 0})
                return
            seen.add(mod)
            dc = strip(prj_safeio.read_text(root, dr))
            bad.extend(forbidden(dc, dr))
            visit(dr, dc, (*chain, mod))
            order.append((mod, dr, p))
    visit(rel, code, ())
    return order, bad


def _messages(out: str, rel: str, lines: int, names: list[str]) -> tuple[list[str], dict]:
    """The compiler's JSON messages → (errors, {theorem: [axioms]}); the appended lines' answers are the axioms."""
    errors, axioms = [], {}
    for raw in out.splitlines():
        try:
            m = json.loads(raw)
        except ValueError:
            if raw.strip():
                errors.append(raw.strip())
            continue
        if not isinstance(m, dict):
            continue
        line = int((m.get("pos") or {}).get("line") or 0)
        data = str(m.get("data", "")).strip()
        fname = str(m.get("fileName", ""))
        mine = fname == "<stdin>"
        if mine and line > lines:                         # one of the `#print axioms` lines Aurora appended
            a = AXIOMS.match(data)
            k = line - lines - 1
            if a and 0 <= k < len(names):
                axioms[names[k]] = [x.strip() for x in (a.group(2) or "").split(",") if x.strip()]
            elif m.get("severity") == "error" and 0 <= k < len(names):
                errors.append(f"axioms of {names[k]} not printed: {data[:300]}")
            continue
        if m.get("severity") == "error":
            where = rel if mine else fname
            errors.append(f"{where}:{line}:{(m.get('pos') or {}).get('column', 0)}: {data}")
    return errors, axioms


def _trim(errors: list[str]) -> list[str]:
    out, room = [], ERR_CHARS
    for e in errors:
        if room <= 0:
            out.append(f"… {len(errors) - len(out)} more")
            break
        out.append(e[:room])
        room -= len(out[-1])
    return out


def check(cfg: sys_config.Config, project: str, path: str, record: bool = True) -> dict:
    """The verdict on one .lean file of the project (see the module's docstring); kept in the history when `record`."""
    t0 = time.time()
    r = {"path": str(path or ""), "status": "error", "errors": [], "axioms": {}, "forbidden": [], "theorems": [],
         "seconds": 0.0, "sha256": ""}
    try:
        r.update(_check(cfg, project, str(path or ""), r))
    except ValueError as e:
        r.update(status="refused", errors=[str(e)])
    except (RuntimeError, OSError) as e:
        r.update(status="error", errors=[str(e)])
    r["seconds"] = round(time.time() - t0, 1)
    r["created"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if record:
        try:
            _keep(cfg, project, r)
        except (OSError, ValueError):
            pass
    return r


def _check(cfg: sys_config.Config, project: str, path: str, r: dict) -> dict:
    if not enabled(cfg):
        raise RuntimeError("formal verification is off (AURORA_PROOF_ENABLED)")
    return _in(cfg, prj_run.project_dir(cfg, project).resolve(), path, r)


def _in(cfg: sys_config.Config, root: Path, path: str, r: dict, limit: float | None = None) -> dict:
    """The verdict on the file `path` of the folder `root` (a project's, or check_source's scratch folder)."""
    from . import prj_safeio
    rel, p = _file(root, path)
    src = prj_safeio.read_text(root, rel)
    r.update(path=rel, sha256=hashlib.sha256(src.encode("utf-8")).hexdigest())
    code = strip(src)
    deps, bad = _deps(root, rel, code)
    bad = forbidden(code, rel) + bad
    if bad:
        return {"status": "refused", "forbidden": bad,
                "errors": [f"{b['file']}:{b['line']}: {b['what']}" if b["line"] else f"{b['file']}: {b['what']}"
                           for b in bad][:50]}
    names = declared(code)
    if not names:
        return {"status": "not_proved", "errors": ["no theorem or lemma declared: nothing to prove"]}
    tc = toolchain(cfg)
    lean = shlex.quote(str(tc["lean"]))
    steps = []
    for mod, _, dp in deps:
        out = f"{BUILD}/{mod.replace('.', '/')}"
        steps.append(f"mkdir -p {shlex.quote(str(Path(out).parent))} && {lean} -M {MEMORY_MB} --json -R "
                     f"{shlex.quote(str(root))} -o {shlex.quote(out + '.olean')} -i {shlex.quote(out + '.ilean')} "
                     f"{shlex.quote(str(dp))} || exit 3")
    steps.append(f"exec {lean} -M {MEMORY_MB} --json --stdin")
    lines = src.count("\n") + (0 if src.endswith("\n") else 1)
    body = src + ("" if src.endswith("\n") else "\n") + "".join(f"#print axioms {n}\n" for n in names)
    if not shutil.which("bwrap"):
        raise RuntimeError("bubblewrap (bwrap) is not installed: no cage, nothing is compiled")
    limit = max(1, int(limit or cfg["AURORA_PROOF_TIMEOUT_S"]))
    try:
        done = subprocess.run(cage(cfg, root, tc, "\n".join(steps)), input=body, capture_output=True, text=True,
                              timeout=limit)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"stopped after {limit} s (AURORA_PROOF_TIMEOUT_S)") from None
    errors, axioms = _messages(done.stdout + "\n" + done.stderr, rel, lines, names)
    if done.returncode not in (0, 1) and not errors:
        errors.append(f"lean ended with exit {done.returncode}")
    missing = [n for n in names if n not in axioms]
    extra = {n: [a for a in ax if a not in STANDARD] for n, ax in axioms.items()}
    extra = {n: a for n, a in extra.items() if a}
    errors += [f"axioms of {n} not reported" for n in missing]
    errors += [f"{n} depends on {', '.join(a)} (only {', '.join(STANDARD)} are accepted)" for n, a in extra.items()]
    ok = done.returncode == 0 and not errors
    return {"status": "proved" if ok else "not_proved", "errors": _trim(errors), "axioms": axioms, "theorems": names}


SCRATCH_FILE = "Claim.lean"


def check_source(cfg: sys_config.Config, source: str, limit: float | None = None) -> dict:
    """A Lean source given as text (kno_prove, N144), checked as a project's file is: written to Claim.lean in a
    private scratch folder under AURORA_STATUS_DIR/prove (0700), deleted after; never in a project's history.
    `limit`: the seconds Lean may take (AURORA_PROOF_TIMEOUT_S when not given)."""
    t0 = time.time()
    r = {"path": SCRATCH_FILE, "status": "error", "errors": [], "axioms": {}, "forbidden": [], "theorems": [],
         "seconds": 0.0, "sha256": ""}
    try:
        base = cfg.path("AURORA_STATUS_DIR") / "prove"
        base.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(dir=base) as d:
            root = Path(d).resolve()
            (root / SCRATCH_FILE).write_text(str(source or ""), encoding="utf-8")
            r.update(_in(cfg, root, SCRATCH_FILE, r, limit))
    except ValueError as e:
        r.update(status="refused", errors=[str(e)])
    except (RuntimeError, OSError) as e:
        r.update(status="error", errors=[str(e)])
    r["seconds"] = round(time.time() - t0, 1)
    return r


# ---- the history (the user's state, outside the cage) and the tool ------------------------------------------------
def _history_file(cfg: sys_config.Config, project: str) -> Path:
    return L.place(cfg, "state", cfg.user) / "projects" / project / "proofs.json"


def _keep(cfg: sys_config.Config, project: str, r: dict) -> None:
    f = _history_file(cfg, project)
    rows = history(cfg, project)
    rows.append({k: r.get(k) for k in ("created", "path", "status", "seconds", "sha256", "theorems", "axioms",
                                       "forbidden", "errors")})
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(rows[-HISTORY:], ensure_ascii=False), encoding="utf-8")


def history(cfg: sys_config.Config, project: str) -> list[dict]:
    """The last checks of the project, oldest first."""
    try:
        rows = json.loads(_history_file(cfg, project).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return rows if isinstance(rows, list) else []


def text(r: dict) -> str:
    """A check for a model: the status first, then what backs it."""
    head = {"proved": "PROVED", "not_proved": "NOT PROVED", "refused": "REFUSED", "error": "ERROR"}[r["status"]]
    out = [f"{head}: {r['path']} ({r['seconds']} s)"]
    if r.get("axioms"):
        out.append("axioms: " + "; ".join(f"{n} [{', '.join(a) or 'none'}]" for n, a in r["axioms"].items()))
    if r.get("errors"):
        out.append("\n".join(r["errors"]))
    if r["status"] == "proved":
        out.append("Every theorem is checked by Lean's kernel with the standard axioms only.")
    elif r["status"] == "not_proved":
        out.append("Do not claim this theorem proved: fix the proof and check again.")
    return "\n".join(out)


def offered(cfg: sys_config.Config, goal: str) -> list[dict]:
    """The tool in the agent's form («project» added), offered in a project's phase (its rules in the goal or
    context) when verification is on."""
    if not enabled(cfg) or not any(w in (goal or "") for w in (NAME, "freeze_predictions")):
        return []
    s = json.loads(json.dumps(TOOL["inputSchema"]))
    s["properties"] = {"project": {"type": "string", "description": "the project's name"}, **s["properties"]}
    s["required"] = ["project", *s["required"]]
    return [{"name": NAME, "description": TOOL["description"], "input_schema": s}]


def agent_call(agent, a: dict) -> str:
    project = str(a.get("project") or a.get("name") or "")
    if not project:
        return f"ERROR: {NAME} needs «project» (the project's name) and «path»."
    try:
        out = text(check(agent.cfg, project, str(a.get("path", ""))))
    except (ValueError, OSError) as e:                    # no such project
        return f"ERROR: {e}"
    if isinstance(getattr(agent, "projects", None), set):
        agent.projects.add(project)
    return out
