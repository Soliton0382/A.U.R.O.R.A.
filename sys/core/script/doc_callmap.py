# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Write docs/CALL_MAP.md: who calls what, read from the code, never from memory (owner, 15 Oct: «devi sapere
esattamente cosa fa ogni script, da cosa viene chiamato»; C323: a daily timer of mine I no longer knew about).

- each script: what starts it (a unit written by the installer, a timer it writes itself, publish.sh, another script,
  the API) or «by hand»;
- each library module and WebUI module: who imports it; the ones nobody imports;
- each API route: the module that serves it and who calls it (the WebUI, a script, a plugin); the ones nobody calls.

    python sys/core/script/doc_callmap.py            # write docs/CALL_MAP.md
    python sys/core/script/doc_callmap.py --check    # docs/CALL_MAP.md up to date, every file in MODULE_MAP.md
    python sys/core/script/doc_callmap.py --live     # this machine: the units and timers installed, what they run,
                                                     # the ones no generator of this repository writes (never published)
"""
from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CORE = ROOT / "sys" / "core"
LIB, SCRIPT, WEB, API = CORE / "aurora", CORE / "script", CORE / "webui", CORE / "aurora" / "api"
OUT = ROOT / "docs" / "CALL_MAP.md"
ROUTE = re.compile(r"@router\.(get|post|put|delete|patch|websocket)\(\s*\"([^\"]+)\"")
JS_IMPORT = re.compile(r"""(?:from\s+|import\s*\(\s*)["']([^"']+\.js)["']""")
# the places a script may be started from, besides Python code: shell, units, manifests, the WebUI
TEXT = ("*.sh", "*.json", "*.js", "*.service", "*.timer", "*.html")


def rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def ours(p: Path) -> bool:
    """A published file: never the owner's own extensions (local/, local_*: ignored by git, C308), caches, libraries."""
    r = "/" + rel(p)
    return not any(s in r for s in ("/local/", "/local_", "/__pycache__/", "/vendor/", "/node_modules/", "/.deps/",
                                    "/.bin/"))      # a plugin's own installed libraries (plg_deps): not ours


def code_files() -> list[Path]:
    """Every file of the repository's code (not tests, docs, data, the owner's local/ extensions)."""
    out = [ROOT / "install.sh"]
    skip = ("/tests/", "/.venv", "/venv/")
    # the code only: never the vault, models, data — nor sys/deploy, the units the installer writes on each machine
    for top in (CORE, ROOT / "sys" / "plugins"):
        for pat in ("*.py", *TEXT):
            out += [p for p in top.rglob(pat) if ours(p) and not any(s in "/" + rel(p) for s in skip)]
    # the signed list of hashes names every file and calls none
    return sorted({p for p in out if p.is_file() and p.name != "MANIFEST.json"})


def module_name(p: Path) -> str:
    return ("aurora." + ".".join(p.relative_to(LIB).with_suffix("").parts)).removesuffix(".__init__")


def imports_of(p: Path) -> set[str]:
    """The aurora modules a Python file imports (absolute and relative, `from aurora import x` included)."""
    try:
        tree = ast.parse(p.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return set()
    pkg = module_name(p).rsplit(".", 1)[0] if p.is_relative_to(LIB) and p.name != "__init__.py" else (
        module_name(p) if p.is_relative_to(LIB) else "")
    got = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            got |= {a.name for a in n.names if a.name.startswith("aurora")}
        elif isinstance(n, ast.ImportFrom):
            base = n.module or ""
            if n.level:
                parts = pkg.split(".")
                base = ".".join(parts[:len(parts) - n.level + 1] + ([n.module] if n.module else []))
            if base.startswith("aurora"):
                got.add(base)
                got |= {f"{base}.{a.name}" for a in n.names}
    return got


def lib_imports(files: list[Path]) -> tuple[list[str], dict[str, set[str]]]:
    mods = sorted(module_name(p) for p in LIB.rglob("*.py") if ours(p))
    known = set(mods)
    by = defaultdict(set)
    for f in [p for p in files if p.suffix == ".py"] + sorted((CORE / "tests").glob("*.py")):
        me = module_name(f) if f.is_relative_to(LIB) else rel(f)
        for m in imports_of(f) & known:
            if m != me:
                by[m].add(me)
    # loaded by name, not by an import line: the API's routers (api/__init__.MODULES) and the firewall's drivers (KINDS)
    for pkg, var in (("api", "MODULES"), ("fw_drivers", "KINDS")):
        init = LIB / pkg / "__init__.py"
        for n in ast.walk(ast.parse(init.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == var for t in n.targets):
                for name in ast.literal_eval(n.value):
                    if f"aurora.{pkg}.{name}" in known:
                        by[f"aurora.{pkg}.{name}"].add(f"aurora.{pkg} ({var})")
    return mods, by


def short(who: str) -> str:
    return who.removeprefix("aurora.").removeprefix("sys/core/")


def script_callers(files: list[Path]) -> dict[str, list[str]]:
    """Each script's name looked for in the rest of the code: who starts it (or imports it)."""
    out = {}
    texts = {f: f.read_text(encoding="utf-8", errors="replace") for f in files}
    for s in sorted(p for p in SCRIPT.iterdir() if p.is_file() and p.suffix in (".py", ".sh")):
        word = re.compile(r"(?<![\w.])" + re.escape(s.stem) + r"(?:\.py|\.sh|\b)")
        out[s.name] = sorted({short(rel(f)) for f, t in texts.items() if f != s and word.search(t)})
    return out


def own_timer(s: Path) -> bool:
    """A script that writes a systemd unit of its own (its --schedule)."""
    t = s.read_text(encoding="utf-8", errors="replace")
    return "OnCalendar" in t or "systemd-run" in t


def routes() -> list[tuple[str, str, str]]:
    out = []
    for p in sorted(API.glob("*.py")):
        for verb, path in ROUTE.findall(p.read_text(encoding="utf-8")):
            out.append((verb.upper(), path, p.stem))
    return out


def route_callers(rs: list[tuple[str, str, str]], files: list[Path]) -> dict[str, list[str]]:
    """Who names a route's path (its {parameters} as anything): the WebUI, scripts, plugins — the API's own files left
    out. A path built piece by piece in the caller (`${base}/x`) is found by its fixed tail."""
    texts = {f: f.read_text(encoding="utf-8", errors="replace") for f in files if not f.is_relative_to(API)}
    out = {}
    for _verb, path, _mod in rs:
        if path in out:
            continue
        rx = re.escape(path)
        rx = re.sub(r"\\\{[^}]*\\\}", r"[^\"'`\\s?]+", rx)
        # a path with parameters may be written with ${…} or by +: the part before the first parameter, then the rest
        head = path.split("{", 1)[0]
        pat = re.compile(rx + r"(?![\w/])") if "{" not in path else re.compile(re.escape(head))
        out[path] = sorted({short(rel(f)) for f, t in texts.items() if pat.search(t)})
    return out


def js_imports() -> tuple[list[str], dict[str, set[str]]]:
    mods = sorted(rel(p).removeprefix("sys/core/webui/") for p in WEB.rglob("*.js") if ours(p))
    by = defaultdict(set)
    for p in WEB.rglob("*.js"):
        if not ours(p):
            continue
        me = rel(p).removeprefix("sys/core/webui/")
        for spec in JS_IMPORT.findall(p.read_text(encoding="utf-8", errors="replace")):
            target = (p.parent / spec).resolve() if spec.startswith(".") else (WEB / spec.lstrip("/")).resolve()
            if target.is_relative_to(WEB.resolve()) and ours(target):
                by[target.relative_to(WEB.resolve()).as_posix()].add(me)
    html = (WEB / "index.html").read_text(encoding="utf-8") if (WEB / "index.html").exists() else ""
    for m in re.findall(r"src=\"/?(?:static/)?([^\"]+\.js)\"", html):
        by[m].add("index.html")
    for p in WEB.rglob("*.js"):                         # the service worker, registered by its address
        for m in re.findall(r"serviceWorker\.register\(\s*[\"']/?([^\"']+\.js)", p.read_text(encoding="utf-8")):
            by[m].add(rel(p).removeprefix("sys/core/webui/"))
    return mods, by


def render() -> str:
    files = code_files()
    mods, by = lib_imports(files)
    scripts = script_callers(files)
    rs = routes()
    rc = route_callers(rs, files)
    jmods, jby = js_imports()
    L = ["# Call map", "",
         "Generated from the code by `sys/core/script/doc_callmap.py` (`--check` in publish.sh): who starts each script, "
         "who imports each module, who calls each API route. What each file does is in MODULE_MAP.md. A file "
         "nobody calls is listed as such: a tool run by hand, a route of an external client, or code to remove.", ""]
    L += ["## Scripts: what starts them", "", "| script | started, imported or named by |", "|---|---|"]
    for name, who in scripts.items():
        tags = (["its own timer (--schedule)"] if own_timer(SCRIPT / name) else [])
        who = [w for w in who if not w.startswith("script/doc_callmap")]
        L.append(f"| `{name}` | {', '.join(tags + [f'`{w}`' for w in who]) or 'by hand'} |")
    L += ["", "## Library modules: who imports them", "",
          "Tests are counted apart: a module imported only by tests is not used by Aurora.", "",
          "| module | imported by (code) | tests |", "|---|---|---|"]
    for m in mods:
        code = sorted(short(x) for x in by.get(m, ()) if not x.startswith("sys/core/tests/"))
        tests = sum(1 for x in by.get(m, ()) if x.startswith("sys/core/tests/"))
        L.append(f"| `{short(m)}` | {', '.join(f'`{c}`' for c in code) or '**nobody**'} | {tests} |")
    L += ["", "## WebUI modules: who imports them", "", "| module | imported by |", "|---|---|"]
    for m in jmods:
        who = sorted(jby.get(m, ()))
        L.append(f"| `{m}` | {', '.join(f'`{w}`' for w in who) or '**nobody** (service worker or page script)'} |")
    L += ["", "## API routes: who calls them", "",
          "Callers are found by the route's path in the WebUI, the scripts and the plugins; a route with nobody is "
          "called from outside (a phone, a client, a webhook) or by a path built at run time.", "",
          "| route | served by | called by |", "|---|---|---|"]
    for verb, path, mod in rs:
        L.append(f"| {verb} `{path}` | `api/{mod}.py` | {', '.join(f'`{w}`' for w in rc[path]) or '—'} |")
    lost = [m for m in mods if not [x for x in by.get(m, ()) if not x.startswith("sys/core/tests/")]
            and not m.endswith("__main__")]
    L += ["", f"Modules nobody in the code imports: {len(lost)}; routes nobody in the repository names: "
          f"{sum(1 for _v, p, _m in rs if not rc[p])} of {len(rs)}.", ""]
    return "\n".join(L)


def unmapped() -> list[str]:
    """Files of the library, the scripts and the WebUI that MODULE_MAP.md never names."""
    text = (ROOT / "docs" / "MODULE_MAP.md").read_text(encoding="utf-8")
    text = re.sub(r"([\w/.-]*)\{([\w,.-]+)\}([\w.]*)",            # js/modules/{a,b}.js: each one named
                  lambda m: " ".join(m.group(1) + x + m.group(3) for x in m.group(2).split(",")), text)
    api_row = next((x for x in text.splitlines() if x.startswith("| `api/*.py`")), "")
    files = [p for p in LIB.rglob("*.py") if ours(p) and p.name != "__init__.py"]
    files += [p for p in SCRIPT.iterdir() if p.is_file() and p.suffix in (".py", ".sh")]
    files += [p for p in WEB.rglob("*.js") if ours(p)]
    out = []
    for p in files:
        names = {p.name, p.relative_to(CORE).as_posix()} | ({p.stem} if "_" in p.stem else set())
        if p.is_relative_to(API):                      # «core», «auth»: only as api/core
            names = {f"api/{p.name}", f"api/{p.stem}", p.relative_to(CORE).as_posix()}
        elif p.is_relative_to(WEB):
            names |= {p.relative_to(WEB).as_posix()}
        if p.is_relative_to(API) and re.search(r"(?<![\w-])" + re.escape(p.stem) + r"(?![\w-])", api_row):
            continue
        if not any(re.search(r"(?<![\w-])" + re.escape(n) + r"(?![\w-])", text) for n in names):
            out.append(rel(p))
    return sorted(out)


def live() -> int:
    """This machine's units and timers named aurora*: what each runs, whether this repository writes it. Printed only:
    it holds this machine's paths and times, never a public file."""
    gen = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in code_files() if p.suffix in (".py", ".sh"))
    for scope, args in (("system", []), ("user", ["--user"])):
        try:
            names = subprocess.run(["systemctl", *args, "list-unit-files", "aurora*", "--no-legend", "--plain"],
                                   capture_output=True, text=True, timeout=20).stdout.split()
        except (OSError, subprocess.SubprocessError):
            continue
        for unit in [n for n in names if n.endswith((".service", ".timer", ".socket", ".target"))]:
            show = subprocess.run(["systemctl", *args, "show", unit, "-p", "ExecStart", "-p", "TimersCalendar",
                                   "-p", "ActiveState", "-p", "FragmentPath"], capture_output=True, text=True,
                                  timeout=20).stdout
            run = re.search(r"argv\[\]=([^;]+)", show)
            what = run.group(1).strip() if run else ""
            script = re.search(r"script/(\w+\.(?:py|sh))", what)
            stem = unit.split("@")[0].rsplit(".", 1)[0]
            ours = stem in gen or (script and (SCRIPT / script.group(1)).exists())
            missing = script and not (SCRIPT / script.group(1)).exists()
            cal = re.search(r"TimersCalendar=\{ OnCalendar=([^;]+)", show)
            state = re.search(r"ActiveState=(\w+)", show)
            print(f"{scope:6} {unit:34} {state.group(1) if state else '':9} "
                  f"{'MISSING SCRIPT ' if missing else ''}{'' if ours else 'NOT FROM THIS REPO '}"
                  f"{cal.group(1).strip() if cal else ''} {what[:110]}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--live", action="store_true")
    a = ap.parse_args()
    if a.live:
        return live()
    text = render()
    if a.check:
        bad = unmapped()
        stale = not OUT.exists() or OUT.read_text(encoding="utf-8") != text
        for f in bad:
            print(f"not in docs/MODULE_MAP.md: {f}")
        if stale:
            print("docs/CALL_MAP.md is not the code's: python sys/core/script/doc_callmap.py")
        return 1 if bad or stale else 0
    OUT.write_text(text, encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: {text.count(chr(10))} lines; not in MODULE_MAP.md: {len(unmapped())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
