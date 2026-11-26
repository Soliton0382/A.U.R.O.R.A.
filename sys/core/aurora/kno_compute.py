# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🧮 Compute instead of remembering (the owner, 26 Nov: «tutti questi strumenti… aurora li può e deve usare se
arrivano domande in chat… strumenti potenti per rispondere a domande complesse senza passare dalla conoscenza del
modello, sia esso locale o Claude»).

The chat's agent gets the tool `compute`: a short Python program it writes, run in the projects' cage (prj_run.cage,
read only: no network, no home, no Aurora folder, a private /tmp, the machine's limits), with NumPy, SciPy, SymPy and
mpmath from Aurora's own environment; with `fem: true` the program runs on FEniCSx's Python instead (dolfinx, gmsh,
NumPy, SciPy; N155). The program's printed output comes back to the agent, which answers from it. Offered in every
chat with a known person (never the anonymous one) when AURORA_COMPUTE_ENABLED; each run at most
AURORA_COMPUTE_TIMEOUT_S seconds. Nothing of the program stays: its folder is a temporary one, deleted after."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from . import prj_run, sys_config, sys_context

NAME = "compute"
CODE_CHARS = 20000
OUT_CHARS = 8000

TOOL = {"name": NAME, "description": (
    "Run a short Python 3 program and get what it prints. Use it for ANY calculation, unit conversion, numerical "
    "estimate, symbolic algebra or calculus, equation solving, statistics, or a check of a formula — never give a "
    "numeric or symbolic result from memory when this tool can compute it, and say in the answer that it was "
    "computed. Available: numpy, scipy, sympy, mpmath (and, with fem=true, FEniCSx: dolfinx 0.9, ufl, gmsh, "
    "petsc4py, mpi4py for finite elements — Poisson, magnetostatics, eddy currents, elasticity, heat; check a case "
    "with a known exact solution first). No network, no files of the user, no GPU; at most a minute. Print the "
    "numbers you need, with their units."),
    "input_schema": {"type": "object", "properties": {
        "code": {"type": "string", "description": "the whole Python program; print() what you need"},
        "fem": {"type": "boolean", "description": "true to run it with FEniCSx's Python (finite elements)"}},
        "required": ["code"]}}


def enabled(cfg: sys_config.Config) -> bool:
    return bool(cfg["AURORA_COMPUTE_ENABLED"])


def offered(cfg: sys_config.Config, goal: str) -> list[dict]:
    """Always in a chat with a known person (the tool is cheap to offer); never in the anonymous chat; not where there
    is no cage (bubblewrap: Linux only — on macOS and Windows the chat answers as before)."""
    if not enabled(cfg) or sys_context.anonymous_now() or not shutil.which("bwrap"):   # no cage, no tool (ports)
        return []
    return [TOOL]


def run(cfg: sys_config.Config, code: str, fem: bool = False) -> dict:
    """{"exit", "seconds", "output"} of the program in the read-only cage; ValueError for an empty or long program,
    RuntimeError when no cage (bwrap) or FEniCSx was asked and is not installed."""
    code = str(code or "")
    if not code.strip() or len(code) > CODE_CHARS:
        raise ValueError(f"a program of 1 to {CODE_CHARS} characters")
    if not shutil.which("bwrap"):
        raise RuntimeError("bubblewrap (bwrap) is not installed: no cage, nothing is run")
    if fem and not prj_run.fem_home(Path(__import__("sys").prefix).parent):
        raise RuntimeError("FEniCSx is not installed (bash sys/core/script/sys_fem_install.sh)")
    limit = int(cfg["AURORA_COMPUTE_TIMEOUT_S"])
    box = Path(tempfile.mkdtemp(prefix="aurora-compute-"))
    try:
        (box / "main.py").write_text(code, encoding="utf-8")
        py = '"$FEM_PYTHON"' if fem else "python3"
        t0 = time.time()
        proc = subprocess.Popen(prj_run.cage(cfg, box, f"{py} -I main.py", readonly=True), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True, start_new_session=True)
        try:
            out, _ = proc.communicate(timeout=limit)
            code_rc = proc.returncode
        except subprocess.TimeoutExpired:
            import os
            import signal
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            out, _ = proc.communicate()
            code_rc = -1
            out = f"{out or ''}\nSTOPPED after {limit} s (AURORA_COMPUTE_TIMEOUT_S)"
        out = (out or "").strip()
        return {"exit": code_rc, "seconds": round(time.time() - t0, 1),
                "output": out if len(out) <= OUT_CHARS else out[:OUT_CHARS] + "\n… (cut)"}
    finally:
        shutil.rmtree(box, ignore_errors=True)


def text(r: dict) -> str:
    head = "OK" if r["exit"] == 0 else f"FAILED (exit {r['exit']})"
    return f"{head} in {r['seconds']} s\n{r['output'] or '(nothing printed)'}"


def agent_call(agent, a: dict) -> str:
    if sys_context.anonymous_now():
        return f"ERROR: {NAME} is not available in the anonymous chat"
    try:
        return text(run(agent.cfg, a.get("code", ""), bool(a.get("fem"))))
    except (ValueError, RuntimeError, OSError) as e:
        return f"ERROR: {e}"


# ---- the short path: the model writes the program, the cage runs it, the model answers from the output -----------
# (27 Nov, measured: through the tools' agent a computation failed whenever the cloud was out — 184 tools do not fit
# the local model's window; this path is two short calls and fits it)
SYS_CODE = ("You write ONE Python 3 program that computes the answer to the owner's question exactly. Use numpy, "
            "scipy, sympy or mpmath when useful{fem}. Print every number the answer needs, with its unit; nothing is "
            "read from files or the network. Reply with the program only, in one ```python block.")
FEM_NOTE = ("; for finite elements use FEniCSx (dolfinx 0.9, ufl, gmsh, petsc4py, mpi4py) and first check a case "
            "whose exact solution is known")
SYS_ANSWER = ("Answer the owner's question in the question's language, briefly, from the OUTPUT of the program that "
              "computed it. Use only numbers that are in the OUTPUT; give the units; say the result was computed. If "
              "the OUTPUT shows an error, say the computation did not succeed and why.")
CODE = __import__("re").compile(r"```(?:python|py)?\s*\n(.*?)```", __import__("re").S)


def _model(cfg):
    from . import mdl_router
    return mdl_router.model_for("agent", mdl_router.base(cfg), cfg)


def solve(cfg, question: str, fem: bool = False, emit=None) -> dict:
    """{"text", "code", "output", "ok"}: the question computed in the cage; at most two programs (the second sees the
    first one's error)."""
    m = _model(cfg)
    system, user, r, code = SYS_CODE.format(fem=FEM_NOTE if fem else ""), f"QUESTION: {question}", None, ""
    for attempt in (1, 2):
        reply = m.complete(system, user, 1500).answer
        got = CODE.search(reply or "")
        code = (got.group(1) if got else reply or "").strip()
        if emit:
            emit("compute.program", {"attempt": attempt, "chars": len(code)})
        try:
            r = run(cfg, code, fem)
        except (ValueError, RuntimeError) as e:
            r = {"exit": -1, "seconds": 0.0, "output": f"ERROR: {e}"}
        if emit:
            emit("compute.run", {"attempt": attempt, "exit": r["exit"], "seconds": r["seconds"]})
        if r["exit"] == 0:
            break
        user = f"QUESTION: {question}\n\nYOUR PROGRAM:\n{code}\n\nIT FAILED:\n{r['output'][-2000:]}\n\nFix it."
    ans = m.complete(SYS_ANSWER, f"QUESTION: {question}\n\nOUTPUT:\n{r['output']}", 700).answer.strip()
    return {"text": ans, "code": code, "output": r["output"], "ok": r["exit"] == 0}


def chat_text(res: dict) -> str:
    """The answer, then the program and its output folded (md.js draws «```python fold» collapsed)."""
    body = res["code"].replace("```", "`` `")
    out = res["output"].replace("```", "`` `")
    return f"{res['text']}\n\n```python fold\n{body}\n# --- output ---\n# " + "\n# ".join(out.splitlines()[:40]) + "\n```"


SYS_IS = ("Decide whether the owner's message asks for a NUMBER or a FORMULA that must be worked out: arithmetic, "
          "units, an equation to solve, an integral or derivative, statistics, a physics or engineering value from "
          "given data. Reply COMPUTE if so; reply NO for a definition, an explanation, history, news, small talk, or "
          "anything about the owner's services. Examples: 'quanto fa 17 alla 13?' COMPUTE; 'risolvi x^2-5x+6=0' "
          "COMPUTE; 'frequenza di un LC con 10 mH e 1 µF?' COMPUTE; 'quanti secondi in 3 settimane?' COMPUTE; "
          "'cos'è un integrale?' NO; 'chi era Fermi?' NO; 'che tempo fa domani?' NO. Reply with exactly one word.")


def wants(model, question: str) -> bool:
    """One token where the model can (M199), else words: is this a computation?"""
    sure = getattr(model, "decide", lambda *a: None)(SYS_IS, f"MESSAGE: {question}", ["COMPUTE", "NO"])
    if sure:
        return sure["COMPUTE"] > 0.5
    return model.complete(SYS_IS, f"MESSAGE: {question}", 4).answer.strip().upper().startswith("COMPUTE")
