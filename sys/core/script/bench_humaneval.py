# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""HumanEval (openai/openai_humaneval, 164 problems): a Python function from its signature and docstring, right
when the set's own tests pass (owner, 2026-10-19: «costruisci IFEval e HumanEval»). Read by bench_public_data.

The answer's last Python block is taken: the whole function (put after the prompt, so the prompt's imports and
helpers stay) or only its body (put under the prompt). Then the set's test and check(<entry point>) run in
prj_run's cage — no network, no home, no environment — at most SECONDS; pass@1, one answer a problem. Without
bubblewrap, or with one that cannot start (a CI runner without user namespaces), nothing is run and the run says so:
the code of a model is never run outside the cage.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aurora.prj_run import cage  # noqa: E402

SECONDS = 20
TAIL = ("\n\nComplete this Python function. Reply with the whole function, its imports included, in one ```python "
        "block.")


def code(answer: str) -> str:
    """The last fenced block (python or none), else the whole answer."""
    blocks = re.findall(r"```(?:python|py|Python)?[ \t]*\n(.*?)```", answer, re.S)
    return blocks[-1] if blocks else answer


def program(item: dict, answer: str) -> str:
    body = code(answer)
    if re.search(rf"^\s*def {re.escape(item['entry_point'])}\s*\(", body, re.M):
        whole = item["header"] + "\n\n" + textwrap.dedent(body)
    else:                                                # only the body: under the signature
        whole = item["header"] + body
    return f"{whole}\n\n{item['test']}\n\ncheck({item['entry_point']})\n"


_works: list[bool] = []


def cage_works() -> bool:
    """bwrap there and allowed to make its namespaces (a CI runner may have it and refuse them: «loopback: not
    permitted»); asked once."""
    if not _works:
        ok = False
        if shutil.which("bwrap"):
            with tempfile.TemporaryDirectory(prefix="aurora-humaneval-") as d:
                try:
                    r = subprocess.run(cage(None, Path(d), "python3 -c 0"), capture_output=True, timeout=SECONDS)
                    ok = r.returncode == 0
                except (OSError, subprocess.TimeoutExpired):
                    ok = False
        _works.append(ok)
    return _works[0]


def score(item: dict, answer: str, judge=None) -> dict:
    if not cage_works():                                 # a cage that cannot start is never a model's wrong answer
        raise RuntimeError("the cage (bubblewrap) does not start here: a model's code is never run outside it")
    with tempfile.TemporaryDirectory(prefix="aurora-humaneval-") as d:
        folder = Path(d)
        (folder / "solution.py").write_text(program(item, answer), encoding="utf-8")
        try:
            r = subprocess.run(cage(None, folder, "python3 solution.py"), capture_output=True, text=True,
                               timeout=SECONDS)
            ok, why = r.returncode == 0, (r.stderr.strip().splitlines() or [""])[-1][:200]
        except subprocess.TimeoutExpired:
            ok, why = False, f"more than {SECONDS} s"
    return {"right": ok, "got": "passed" if ok else why or "failed"}


def items(rows: list[dict]) -> list[dict]:
    return [{"id": r["task_id"], "kind": "code", "answer": "the set's tests pass", "header": r["prompt"],
             "test": r["test"], "entry_point": r["entry_point"], "prompt": f"```python\n{r['prompt']}```{TAIL}"}
            for r in rows]
