# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A name no scope defines fails only when that line runs: in a live call, in front of the owner (C499). Every function
of the code is checked here, with no import: what it reads as a global must exist at its module's level."""
import builtins
import symtable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMPLICIT = {"__file__", "__name__", "__doc__", "__package__", "__spec__", "__path__", "__class__"}


def _undefined(table, known: set[str], out: list[str], where: str) -> None:
    for s in table.get_symbols():
        if table.get_type() != "module" and s.is_referenced() and s.is_global() and s.get_name() not in known:
            out.append(f"{where}:{table.get_lineno()} {table.get_name()}: {s.get_name()}")
    for child in table.get_children():
        _undefined(child, known, out, where)


def test_every_global_read_exists():
    out: list[str] = []
    files = [*(ROOT / "aurora").rglob("*.py"), *(ROOT / "script").rglob("*.py")]
    assert len(files) > 100
    for f in files:
        src = f.read_text(encoding="utf-8")
        table = symtable.symtable(src, str(f), "exec")
        known = {s.get_name() for s in table.get_symbols()} | set(dir(builtins)) | IMPLICIT
        for child in table.get_children():     # `global x` in a function defines it at module level too
            known |= _assigned_global(child)
        _undefined(table, known, out, f.relative_to(ROOT).as_posix())
    assert not out, "\n".join(sorted(out))


def _assigned_global(table) -> set[str]:
    found = {s.get_name() for s in table.get_symbols() if s.is_declared_global()}
    for child in table.get_children():
        found |= _assigned_global(child)
    return found
