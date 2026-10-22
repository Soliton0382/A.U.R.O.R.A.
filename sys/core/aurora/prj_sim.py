# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🧮 A project's simulators (ROADMAP N42; owner, 23 Oct: «un bel simulatore che permette di dimensionare i parametri»).

A simulator is a file <project>/sim/<name>.json written by Aurora (or by hand): the parameters with their range, the
outputs as formulas of the parameters and of the outputs above them, an optional sweep to plot, and notes that say
what the model leaves out. The browser evaluates the formulas (project_sim_expr.js) while the sliders move; here the
file is read and checked, so that a formula with an unknown name or a forbidden construct never reaches the page.

{"title": "...", "notes": "...", "params": [{"id": "N", "label": "spire", "unit": "", "min": 10, "max": 400,
 "step": 10, "value": 100}], "outputs": [{"id": "R", "label": "resistenza", "unit": "ohm", "expr": "rho*L/A",
 "digits": 3}], "consts": {"rho": 1.68e-8}, "plot": {"x": "N", "y": ["R"]}}
"""
from __future__ import annotations

import ast
import json
import math
import re

from . import prj_policy, sys_config

FUNCS = {"sqrt", "abs", "min", "max", "sin", "cos", "tan", "asin", "acos", "atan", "atan2", "exp", "log", "log10",
         "floor", "ceil", "round", "if"}
CONSTS = {"pi": math.pi, "e": math.e, "mu0": 4e-7 * math.pi}
ID = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,31}")
NODES = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Call, ast.Name, ast.Load, ast.Constant, ast.Compare,
         ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.USub, ast.UAdd, ast.Lt, ast.LtE, ast.Gt, ast.GtE)
MAX_SIMS, MAX_ITEMS, MAX_EXPR = 12, 60, 400


def check_expr(expr: str, known: set[str]) -> None:
    """Raise ValueError unless expr is arithmetic over known names and FUNCS (^ is the power, as in the page)."""
    if not isinstance(expr, str) or not expr.strip() or len(expr) > MAX_EXPR:
        raise ValueError("empty or too long formula")
    try:
        tree = ast.parse(expr.replace("^", "**").replace("if(", "if_("), mode="eval")
    except SyntaxError as e:
        raise ValueError(f"formula not understood: {expr}") from e
    called = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    for n in ast.walk(tree):
        if not isinstance(n, NODES):
            raise ValueError(f"not allowed in a formula: {type(n).__name__}")
        if isinstance(n, ast.Compare) and len(n.ops) != 1:
            raise ValueError("one comparison at a time")
        if isinstance(n, ast.Constant) and not isinstance(n.value, (int, float)):
            raise ValueError("only numbers in a formula")
        if isinstance(n, ast.Call):
            if not isinstance(n.func, ast.Name) or n.func.id.replace("if_", "if") not in FUNCS or n.keywords:
                raise ValueError(f"unknown function in: {expr}")
        elif isinstance(n, ast.Name) and id(n) not in called and n.id not in known and n.id not in CONSTS:
            raise ValueError(f"unknown name {n.id} in: {expr}")


def _num(v, what: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ValueError(f"{what}: a number")
    return float(v)


def check(spec: dict) -> dict:
    """The simulator as the page needs it, or ValueError saying what is wrong."""
    if not isinstance(spec, dict):
        raise ValueError("not an object")
    consts = spec.get("consts") or {}
    if not isinstance(consts, dict) or len(consts) > MAX_ITEMS:
        raise ValueError("consts: an object")
    known = set(CONSTS)
    out = {"title": str(spec.get("title") or "")[:120], "notes": str(spec.get("notes") or "")[:4000],
           "consts": {}, "params": [], "outputs": []}
    for k, v in consts.items():
        if not ID.fullmatch(k) or k in known:
            raise ValueError(f"bad constant name {k}")
        out["consts"][k] = _num(v, k)
        known.add(k)
    params, outputs = spec.get("params") or [], spec.get("outputs") or []
    if not isinstance(params, list) or not isinstance(outputs, list) or not params or not outputs \
            or len(params) > MAX_ITEMS or len(outputs) > MAX_ITEMS:
        raise ValueError("params and outputs: 1 to 60 each")
    for p in params:
        pid = str((p or {}).get("id", ""))
        if not ID.fullmatch(pid) or pid in known or pid in FUNCS:
            raise ValueError(f"bad parameter id {pid}")
        lo, hi = _num(p.get("min"), pid), _num(p.get("max"), pid)
        val, step = _num(p.get("value", lo), pid), _num(p.get("step", (hi - lo) / 100 or 1), pid)
        if not lo < hi or not lo <= val <= hi or step <= 0:
            raise ValueError(f"{pid}: min < max, value inside, step > 0")
        out["params"].append({"id": pid, "label": str(p.get("label") or pid)[:80], "unit": str(p.get("unit") or "")[:20],
                              "min": lo, "max": hi, "step": step, "value": val, "group": str(p.get("group") or "")[:40]})
        known.add(pid)
    for o in outputs:
        oid = str((o or {}).get("id", ""))
        if not ID.fullmatch(oid) or oid in known or oid in FUNCS:
            raise ValueError(f"bad output id {oid}")
        check_expr(o.get("expr"), known)
        digits = int(_num(o.get("digits", 3), oid))
        out["outputs"].append({"id": oid, "label": str(o.get("label") or oid)[:80], "unit": str(o.get("unit") or "")[:20],
                               "expr": o["expr"], "digits": max(1, min(digits, 8)), "group": str(o.get("group") or "")[:40],
                               "hidden": bool(o.get("hidden"))})
        known.add(oid)
    plot = spec.get("plot")
    if plot:
        ys = plot.get("y") if isinstance(plot, dict) else None
        ys = [ys] if isinstance(ys, str) else ys
        ids = {o["id"] for o in out["outputs"]}
        if plot.get("x") not in {p["id"] for p in out["params"]} or not ys or not set(ys) <= ids or len(ys) > 4:
            raise ValueError("plot: x a parameter, y 1 to 4 outputs")
        out["plot"] = {"x": plot["x"], "y": list(ys)}
    return out


def sims(cfg: sys_config.Config, project: str) -> list[dict]:
    """The project's simulators; a file that does not pass is listed with its error, not hidden."""
    if not prj_policy.NAME.fullmatch(project or ""):
        raise ValueError("bad name")
    root = cfg.path("AURORA_PROJECTS_DIR") / project
    if not root.is_dir():
        raise ValueError("no such project")
    folder = root / "sim"
    out = []
    for f in sorted(folder.glob("*.json"))[:MAX_SIMS] if folder.is_dir() else []:
        if not prj_policy.NAME.fullmatch(f.stem):
            continue
        try:
            out.append({"name": f.stem, **check(json.loads(f.read_text(encoding="utf-8")))})
        except (OSError, ValueError) as e:
            out.append({"name": f.stem, "error": str(e)[:300]})
    return out
