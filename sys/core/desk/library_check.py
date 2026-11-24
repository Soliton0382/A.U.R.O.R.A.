# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N152: the general library's format check (design §7, rules V1-b and V1-h). A procedure is a closed JSON schema:
an unknown field makes it invalid (never ignored), a field that would widen what Aurora may do makes it invalid, and
a step's declared class may never be lower than the class computed from the step itself.

    python3 -I check: python3 -I sys/core/desk/library_check.py [library dir]      exit 1 on any invalid file"""
import json
import re
import sys
from pathlib import Path

LIBRARY = Path(__file__).resolve().parent / "library"
UNKNOWN_VERSION = "sconosciuta"                                         # bozza 8 §4: per: only
CLASSES = ["legge", "scrive in locale", "esce", "irreversibile"]          # increasing severity (design bozza 2 §5.2)
OSES = {"linux", "windows"}
# fields that would add programs, sites, folders, trusted entries or exceptions (V1-h): their presence = invalid
WIDENING = {"programs", "sites", "origins", "folders", "trusted", "trust", "allow", "allowlist", "exclusions",
            "exceptions", "permissions", "class_override", "network_override", "sudo", "elevated", "install"}
TOP = {"format", "id", "title", "os", "program", "params", "steps", "notes"}
PROGRAM = {"name", "package", "exe", "versions", "network", "launch"}
LAUNCH = {"exe", "args"}
VERSIONS = {"min", "below"}
PARAM = {"kind", "max", "chars", "must_not_exist"}
KINDS = {"text", "path", "name"}
STEP = {"n", "do", "target", "text", "keys", "keys_map", "class", "expect", "timeout_s", "into"}
DO = {"wait", "open_menu", "press", "press_each", "type", "key", "read", "read_list"}
READ_ONLY_DO = {"wait", "open_menu", "read", "read_list"}             # the closed list that may be «legge»
TARGET = {"role", "id", "id_end", "name", "name_re", "offscreen_ok", "in_dialog"}
EXPECT = {"present", "gone"}
# a target named with one of these verbs is always «irreversibile» (design bozza 2 §5.2, rule R20)
IRREVERSIBLE = re.compile(r"(?i)\b(elimin|cancell|sovrascriv|svuot|revoc|disinstall|installa|delet|remov|overwrit"
                          r"|empty|revok|uninstall|install|format)")
# a target named with one of these verbs leaves the machine
LEAVES = re.compile(r"(?i)\b(invia|condividi|pubblica|carica|send|share|publish|upload|post\b|submit)")


def _keys(where: str, obj, allowed: set, errs: list) -> None:
    if not isinstance(obj, dict):
        errs.append(f"{where}: not an object")
        return
    for k in obj:
        if k in WIDENING:
            errs.append(f"{where}: field {k!r} would widen what Aurora may do (V1-h)")
        elif k not in allowed:
            errs.append(f"{where}: unknown field {k!r}")


def _names(t: dict) -> list:
    out = []
    for f in ("name", "name_re"):
        v = t.get(f)
        if isinstance(v, dict):
            out += [str(x) for x in v.values()]
    return out


def _target(where: str, t, errs: list) -> None:
    _keys(where, t, TARGET, errs)
    if isinstance(t, dict) and not isinstance(t.get("role"), str):
        errs.append(f"{where}: role missing")


def computed_class(step: dict, network: bool) -> str:
    """The least severe class this step may carry; the declared one must be at least this."""
    do = step.get("do")
    names = _names(step.get("target") or {})
    if any(IRREVERSIBLE.search(n) for n in names):
        return "irreversibile"
    if any(LEAVES.search(n) for n in names):
        return "esce"
    if do in READ_ONLY_DO:
        return "legge"
    if network:                                    # with a network every click, key and write may leave
        return "esce"
    return "scrive in locale"


def check(path: Path, root: Path = LIBRARY, ns: str = "gen") -> list:
    errs = []
    if path.suffix != ".json":
        return [f"{path.name}: only .json procedures in the library (V1-b: no images, nothing unread)"]
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return [f"{path.name}: not JSON ({e})"]
    _keys("procedure", d, TOP, errs)
    if not isinstance(d, dict):
        return errs
    if ns not in ("gen", "per"):
        errs.append(f"namespace must be gen or per, not {ns!r}")
    if d.get("format") != 1:
        errs.append("format must be 1")
    os_ = d.get("os")
    if os_ not in OSES:
        errs.append(f"os must be one of {sorted(OSES)}")
    prog = d.get("program") or {}
    _keys("program", prog, PROGRAM, errs)
    if isinstance(prog, dict):
        if not isinstance(prog.get("network"), bool):
            errs.append("program.network must be true or false (declared, never guessed)")
        _keys("program.launch", prog.get("launch") or {}, LAUNCH, errs)
        _keys("program.versions", prog.get("versions") or {}, VERSIONS, errs)
        vmin = (prog.get("versions") or {}).get("min")
        if not vmin:
            errs.append("program.versions.min missing (V1-g)")
        elif vmin == UNKNOWN_VERSION and ns != "per":
            errs.append("an unknown version is allowed only in a personal procedure (per:)")
    try:
        rel = path.resolve().relative_to(root.resolve())
        want = f"{ns}:{rel.parts[0]}/{'/'.join(rel.parts[1:-1])}/{path.stem}"
        if d.get("id") != want:
            errs.append(f"id must be {want!r} (namespace {ns}:, from its folder)")
        if rel.parts[0] != os_:
            errs.append("os differs from the folder")
    except ValueError:
        errs.append(f"{path.name}: outside the library folder given ({root})")
    params = d.get("params") or {}
    if not isinstance(params, dict):
        errs.append("params: not an object")
        params = {}
    for k, v in params.items():
        _keys(f"params.{k}", v, PARAM, errs)
        if isinstance(v, dict) and v.get("kind") not in KINDS:
            errs.append(f"params.{k}.kind must be one of {sorted(KINDS)}")
    steps = d.get("steps")
    if not isinstance(steps, list) or not steps:
        errs.append("steps missing")
        steps = []
    network = bool(isinstance(prog, dict) and prog.get("network"))
    for i, st in enumerate(steps, 1):
        w = f"step {i}"
        _keys(w, st, STEP, errs)
        if not isinstance(st, dict):
            continue
        if st.get("n") != i:
            errs.append(f"{w}: n must be {i}")
        if st.get("do") not in DO:
            errs.append(f"{w}: do must be one of {sorted(DO)}")
        if st.get("class") not in CLASSES:
            errs.append(f"{w}: class must be one of {CLASSES}")
        elif st.get("do") in DO:
            need = computed_class(st, network)
            if CLASSES.index(st["class"]) < CLASSES.index(need):
                errs.append(f"{w}: class {st['class']!r} is lower than {need!r} (a class only goes up)")
        if st.get("target") is not None:
            _target(f"{w}.target", st["target"], errs)
        elif st.get("do") not in ("wait", "key"):
            errs.append(f"{w}: target missing")
        ex = st.get("expect")
        if ex is not None:
            _keys(f"{w}.expect", ex, EXPECT, errs)
            for k in EXPECT:
                if isinstance(ex, dict) and ex.get(k) is not None:
                    _target(f"{w}.expect.{k}", ex[k], errs)
        for f in ("text",):
            for ref in re.findall(r"\{(\w+)\}", str(st.get(f, ""))):
                if ref not in params:
                    errs.append(f"{w}: {{{ref}}} is not a declared parameter")
    for ref in re.findall(r"\{(\w+)\}", json.dumps((prog or {}).get("launch", {}))):
        if ref not in params:
            errs.append(f"program.launch: {{{ref}}} is not a declared parameter")
    return errs


def check_tree(root: Path = LIBRARY) -> dict:
    out = {}
    for f in sorted(p for p in root.rglob("*") if p.is_file()):
        out[str(f.relative_to(root))] = check(f, root)
    return out


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else LIBRARY
    res = check_tree(root)
    bad = {k: v for k, v in res.items() if v}
    for k, v in res.items():
        print(("ok   " if not v else "BAD  ") + k)
        for e in v:
            print("       " + e)
    print(f"{len(res) - len(bad)}/{len(res)} valid")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
