# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A grid puzzle solved as a verified program (ROADMAP 105, step 3): the model writes the rule as a small Python
function, the function runs in a cage on the examples, and only a rule that reproduces every example is applied to the
test — an answer checked before it is given, not a guessed grid. Anything else (no grids, a rule that fails twice, no
cage) returns None and the problem goes to the reasoning, as before."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROW = re.compile(r"^\s*\d(?:[ \t]+\d)*\s*$")
CODE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.S)
TRIES = 2
SECONDS = 10
SYS_RULE = ("You solve a grid puzzle by writing its rule as a program. The user gives examples of an INPUT grid and its "
            "OUTPUT grid (digits 0-9 are colours) and a TEST input. Find the one rule that turns every input into its "
            "output, and write it as a Python function `def transform(grid: list[list[int]]) -> list[list[int]]` "
            "that works for any grid of this puzzle, the test included — never written for the examples one by one, "
            "never with their outputs copied in. Standard library only. Reply with the code alone, in one ```python "
            "block.")
RUNNER = """import json, sys
sys.setrecursionlimit(10000)
data = json.load(open("data.json"))
ns = {}
exec(open("rule.py").read(), ns)
out = []
for g in data:
    try:
        r = ns["transform"]([row[:] for row in g])
        out.append([[int(v) for v in row] for row in r])
    except Exception as e:
        out.append({"error": f"{type(e).__name__}: {e}"[:300]})
print(json.dumps(out))
"""


def worth(p) -> bool:
    """Only with a cloud model writing the rule: the local one (Qwen3.6 35B) answered 1 puzzle of 6, the other 5 with
    no code after its room of thinking, about 300 s each (M221)."""
    from . import mdl_router
    try:
        return mdl_router.assignments(p.cfg).get("synthesis", {}).get("provider", "local") != "local"
    except Exception:                                  # noqa: BLE001 — no assignment readable: the reasoning, as before
        return False


def grids(text: str) -> list[list[list[int]]]:
    """The grids of a text in order: runs of lines made only of digits."""
    out, cur = [], []
    for line in text.splitlines() + [""]:
        if ROW.match(line):
            cur.append([int(v) for v in line.split()])
        elif cur:
            out.append(cur)
            cur = []
    return out


def puzzle(text: str) -> tuple[list[tuple], list] | None:
    """(examples [(input, output)], test input) of a grid puzzle: an odd number of grids, at least two examples, the
    last one alone; or None."""
    g = grids(text)
    if len(g) < 5 or len(g) % 2 == 0:
        return None
    return [(g[i], g[i + 1]) for i in range(0, len(g) - 1, 2)], g[-1]


def run(code: str, inputs: list) -> list | None:
    """What `transform` returns for each input, run with no network, no home and no environment (prj_run's cage), at
    most SECONDS; None when there is no cage or it does not answer."""
    if not shutil.which("bwrap"):
        return None
    from .prj_run import cage
    with tempfile.TemporaryDirectory(prefix="aurora-grid-") as d:
        folder = Path(d)
        (folder / "rule.py").write_text(code, encoding="utf-8")
        (folder / "data.json").write_text(json.dumps(inputs), encoding="utf-8")
        (folder / "run.py").write_text(RUNNER, encoding="utf-8")
        try:
            r = subprocess.run(cage(None, folder, "python3 run.py"), capture_output=True, text=True, timeout=SECONDS)
            return json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 and r.stdout.strip() else None
        except (subprocess.TimeoutExpired, ValueError, IndexError):
            return None


def show(grid: list) -> str:
    return "\n".join(" ".join(str(v) for v in row) for row in grid)


def solve(p, question: str, ev) -> dict | None:
    """{"text", "sources", "dropped"} with the test's grid from a rule that reproduces every example; or None."""
    found = puzzle(question)
    if not found:
        return None
    examples, test = found
    model, ask = p._for("synthesis"), question
    for attempt in range(1, TRIES + 1):
        out = model.complete(SYS_RULE, ask, 16000, think=True).answer or ""
        if not out.strip():                          # the room ended in the thinking: a second try ends the same
            ev("grid.rule", {"attempt": attempt, "ok": False, "why": "no answer"})
            return None
        m = CODE.search(out)
        code = (m.group(1) if m else out).strip()
        if "def transform" not in code:
            ev("grid.rule", {"attempt": attempt, "ok": False, "why": "no function"})
            continue
        got = run(code, [i for i, _ in examples] + [test])
        if got is None:
            ev("grid.rule", {"attempt": attempt, "ok": False, "why": "did not run"})
            return None
        wrong = [n for n, ((_, o), g) in enumerate(zip(examples, got), 1) if g != o]
        ev("grid.rule", {"attempt": attempt, "ok": not wrong, "wrong": wrong, "examples": len(examples),
                         **({"code": code[:3000]} if not wrong else {})})
        if not wrong and isinstance(got[-1], list) and got[-1]:
            from . import txt_lang
            en = txt_lang.detect(question) == "en"
            note = (f"🧩 Rule found as a program and checked on all {len(examples)} examples:" if en else
                    f"🧩 Regola trovata come programma e verificata su tutti i {len(examples)} esempi:")
            return {"text": f"{note}\n\n{'Answer' if en else 'Risposta'}:\n{show(got[-1])}", "sources": [],
                    "dropped": []}
        n = wrong[0]
        seen = got[n - 1]
        ask = (f"{question}\n\nYour previous rule:\n```python\n{code}\n```\nfails on example {n}: it returns\n"
               f"{show(seen) if isinstance(seen, list) else seen}\ninstead of\n{show(examples[n - 1][1])}\n"
               "Find the rule again.")
    return None
