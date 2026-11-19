# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔭 The symbolic search of the discovery engine (ROADMAP N147), numpy only and no Aurora import: prj_discover sends
this file's source with the training rows (base64 JSON) to python in prj_run's cage, so the search never sees the
held-out rows and never reaches Aurora's folder.

A law is a structure (no text is ever evaluated): a sum of terms, each term a product of factors
{"v": input index, "op": pow | log | sin | cos | exp, "p": exponent}, with constants fitted by least squares.
Families: c0 + c1·g, c1·g, c0 + c1·g1 + c2·g2 (from the best single terms), the power law c·∏ x_i^p_i (log-log fit,
exponents rounded to sixths), the exponential exp(a + b·g) (log |y| fit, y of one sign), and the baselines: the
constant and the linear law. Each structure is scored by 5-fold cross-validation on the training rows; the chosen law
is the simplest whose error is within one standard error of the best (the «one-standard-error rule»); the Pareto
front keeps, for each complexity, the best error that improves on every simpler one.
"""
from __future__ import annotations

import itertools
import math
import time

import numpy as np

POWERS = (-3.0, -2.0, -1.5, -1.0, -0.5, -1 / 3, 1 / 3, 0.5, 1.0, 1.5, 2.0, 3.0)
UNARY = ("log", "sin", "cos", "exp")
FOLDS = 5
TOP_SINGLES = 12                 # single terms kept for the pairs
MIN_ROWS = 8


# ---- one factor, one term, one law -------------------------------------------------------------------------------
def factor(x: np.ndarray, f: dict) -> np.ndarray:
    v = x[:, f["v"]]
    op = f["op"]
    if op == "pow":
        return np.power(v, f["p"])
    if op == "log":
        return np.log(v)
    if op == "sin":
        return np.sin(v)
    if op == "cos":
        return np.cos(v)
    if op == "exp":
        return np.exp(v)
    raise ValueError(op)


def term(x: np.ndarray, t: list) -> np.ndarray:
    out = np.ones(len(x))
    for f in t:
        out = out * factor(x, f)
    return out


def valid(f: dict, x: np.ndarray) -> bool:
    """A factor defined on every row: a non-integer power or a log on positive values only; exp not overflowing."""
    v = x[:, f["v"]]
    if f["op"] == "log" or (f["op"] == "pow" and float(f["p"]).is_integer() is False):
        return bool(np.all(v > 0))
    if f["op"] == "pow" and f["p"] < 0:
        return bool(np.all(v != 0))
    if f["op"] == "exp":
        return bool(np.all(np.abs(v) < 50))
    return True


def complexity(law: dict) -> int:
    """Nodes of the expression: each fitted constant, each factor (its variable and its operation, the exponent when
    it is not 1), the products and sums that join them."""
    n = len(law["c"])
    for t in law["terms"]:
        n += sum(2 + (f["op"] == "pow" and f["p"] != 1.0) for f in t) + max(0, len(t) - 1) + 1
    n += 2 if law["kind"] == "exp" else 0
    return n


def design(x: np.ndarray, law: dict) -> np.ndarray:
    cols = [np.ones(len(x))] if law["intercept"] else []
    cols += [term(x, t) for t in law["terms"]]
    return np.column_stack(cols) if cols else np.zeros((len(x), 0))


def fit(x: np.ndarray, y: np.ndarray, law: dict) -> list | None:
    """The constants by least squares (on log |y| for the exponential family); None when the fit fails."""
    a = design(x, law)
    target = y
    if law["kind"] == "exp":
        if not (np.all(y > 0) or np.all(y < 0)):
            return None
        target = np.log(np.abs(y))
    if a.shape[1] == 0 or not np.all(np.isfinite(a)):
        return None
    try:
        c, *_ = np.linalg.lstsq(a, target, rcond=None)
    except np.linalg.LinAlgError:
        return None
    return [float(v) for v in c] if np.all(np.isfinite(c)) else None


def predict(x: np.ndarray, law: dict, c: list) -> np.ndarray:
    z = design(x, law) @ np.asarray(c, dtype=float)
    if law["kind"] == "exp":
        return law.get("sign", 1.0) * np.exp(np.clip(z, -700, 700))
    return z


def rmse(a: np.ndarray, b: np.ndarray) -> float:
    d = a - b
    return float(math.sqrt(float(np.mean(d * d)))) if len(d) else float("nan")


def cv(x: np.ndarray, y: np.ndarray, law: dict, folds: list, oof: list | None = None) -> tuple[float, float] | None:
    """Mean and standard error of the held-in folds' RMSE (constants refitted on each training part); `oof` receives
    the out-of-fold residuals."""
    errs = []
    for test in folds:
        train = np.setdiff1d(np.arange(len(y)), test)
        c = fit(x[train], y[train], law)
        if c is None:
            return None
        p = predict(x[test], law, c)
        if not np.all(np.isfinite(p)):
            return None
        errs.append(rmse(p, y[test]))
        if oof is not None:
            oof.extend(zip((p - y[test]).tolist(), y[test].tolist()))
    return float(np.mean(errs)), float(np.std(errs, ddof=1) / math.sqrt(len(errs)))


# ---- the candidates ----------------------------------------------------------------------------------------------
def singles(x: np.ndarray) -> list[list]:
    out = []
    for v in range(x.shape[1]):
        for p in POWERS:
            out.append([{"v": v, "op": "pow", "p": float(p)}])
        for op in UNARY:
            out.append([{"v": v, "op": op, "p": 1.0}])
    return [t for t in out if all(valid(f, x) for f in t)]


def power_law(x: np.ndarray, y: np.ndarray) -> list | None:
    """c·∏ x_i^p_i from log |y| = a + Σ p_i log x_i, each p rounded to the nearest sixth (none dropped: a zero p
    leaves its variable out)."""
    if not (np.all(x > 0) and (np.all(y > 0) or np.all(y < 0))):
        return None
    a = np.column_stack([np.ones(len(y)), np.log(x)])
    try:
        b, *_ = np.linalg.lstsq(a, np.log(np.abs(y)), rcond=None)
    except np.linalg.LinAlgError:
        return None
    t = [{"v": i, "op": "pow", "p": round(float(p) * 6) / 6} for i, p in enumerate(b[1:]) if round(float(p) * 6) != 0]
    return t or None


def candidates(x: np.ndarray, y: np.ndarray, max_c: int) -> list[dict]:
    """Every law structure tried (constants not yet fitted), the baselines first."""
    k = x.shape[1]
    laws = [{"kind": "lin", "intercept": True, "terms": [], "name": "constant", "baseline": True},
            {"kind": "lin", "intercept": True, "terms": [[{"v": v, "op": "pow", "p": 1.0}] for v in range(k)],
             "name": "linear", "baseline": True}]
    one = singles(x)
    for t in one:
        laws.append({"kind": "lin", "intercept": False, "terms": [t]})
        laws.append({"kind": "lin", "intercept": True, "terms": [t]})
        laws.append({"kind": "exp", "intercept": True, "terms": [t], "sign": float(np.sign(y[0]) or 1.0)})
    if k >= 2:                                               # products of two inputs' powers
        for (i, j) in itertools.combinations(range(k), 2):
            for p, q in itertools.product((-2.0, -1.0, -0.5, 0.5, 1.0, 2.0), repeat=2):
                t = [{"v": i, "op": "pow", "p": p}, {"v": j, "op": "pow", "p": q}]
                if all(valid(f, x) for f in t):
                    laws.append({"kind": "lin", "intercept": False, "terms": [t]})
    if (t := power_law(x, y)) is not None:
        laws.append({"kind": "lin", "intercept": False, "terms": [t], "from": "log-log"})
    for law in laws:
        law["complexity"] = complexity({**law, "c": [0.0] * (len(law["terms"]) + law["intercept"])})
    return [law for law in laws if law.get("baseline") or law["complexity"] <= max_c]


# ---- the search --------------------------------------------------------------------------------------------------
BOOT = 2000
LEVEL = 0.99
DRAW_CAP = 5000                  # rows per bootstrap draw (C620: 4000 × 140,000 indices were 10 GB)
CHUNK = 100                      # draws per block


def _boot_rmse(r: np.ndarray, size: int, g: np.random.Generator) -> np.ndarray:
    out = np.empty(BOOT)
    for i in range(0, BOOT, CHUNK):
        k = min(CHUNK, BOOT - i)
        out[i:i + k] = np.sqrt(np.mean(r[g.integers(0, len(r), size=(k, size))] ** 2, axis=1))
    return out


def bound(res: list, m: int, seed: int) -> float:
    """The RMSE that m new rows reach at most with probability LEVEL, if they behave like the out-of-fold residuals.
    A bootstrap of the ratio RMSE(m new rows) / RMSE(the n training rows), both drawn from the residuals: the
    uncertainty of the held-out rows AND that of the training error itself (only the first: 13 % of true laws
    failed; a fixed ratio to the CV error: noise that grows with the value failed them too). Each draw at most
    DRAW_CAP rows, in blocks: above it the ratio's spread is overstated a little (the bound looser), memory bounded."""
    r = np.asarray(res, dtype=float)
    g = np.random.default_rng(seed + 1)
    new = _boot_rmse(r, min(max(1, m), DRAW_CAP), g)
    old = _boot_rmse(r, min(len(r), DRAW_CAP), g)
    ratio = new / np.maximum(old, 1e-300)
    return float(rmse(r, np.zeros(len(r))) * np.quantile(ratio, LEVEL))


def metric(oof: list) -> str:
    """«relative» (errors divided by |y|) when that makes the residuals more alike between the rows with small and
    large |y| than the absolute errors do (noise that grows with the value), else «absolute». Training rows only."""
    r = np.asarray(oof, dtype=float)
    res, yy = r[:, 0], np.abs(r[:, 1])
    if np.any(yy == 0) or len(yy) < 8 or not (np.all(r[:, 1] > 0) or np.all(r[:, 1] < 0)):
        return "absolute"                    # C687: y crossing zero makes every relative error blow up near it
    big = yy > np.median(yy)

    def spread(e: np.ndarray) -> float:
        lo, hi = float(np.mean(e[~big] ** 2)), float(np.mean(e[big] ** 2))
        return abs(math.log(max(hi, 1e-300) / max(lo, 1e-300)))
    return "relative" if spread(res / yy) < spread(res) else "absolute"


def fit_relative(x: np.ndarray, y: np.ndarray, law: dict) -> list | None:
    """A linear-family law's constants by least squares weighted 1/y² — the fit that minimises the relative error it
    is scored in (C687: baselines fitted in absolute error and scored in relative error were a straw man)."""
    a = design(x, law)
    if a.shape[1] == 0:
        return []
    if law["kind"] != "lin" or np.any(y == 0) or not np.all(np.isfinite(a)):
        return None
    w = 1.0 / np.abs(y)
    try:
        c, *_ = np.linalg.lstsq(a * w[:, None], y * w, rcond=None)
    except np.linalg.LinAlgError:
        return None
    return [float(v) for v in c] if np.all(np.isfinite(c)) else None


ZERO = {"kind": "lin", "intercept": False, "terms": [], "name": "zero", "baseline": True, "c": []}


def baselines(x: np.ndarray, y: np.ndarray, scored: list, how: str) -> dict:
    """The constant, the linear and the zero law (C687: p = 0, relative error 1 on every row), their constants fitted
    in the metric they are scored in."""
    base = {s["name"]: dict(s) for s in scored if s.get("baseline")}
    base["zero"] = {**ZERO, "complexity": 1, "cv_rmse": rmse(np.zeros(len(y)), y), "cv_se": 0.0,
                    "train_rmse": rmse(np.zeros(len(y)), y)}
    for b in base.values():
        b["fit"] = how
        if how == "relative" and (c := fit_relative(x, y, b)) is not None:
            b["c"] = c
    return base


def errors(p: np.ndarray, y: np.ndarray, how: str) -> np.ndarray:
    return (p - y) / np.abs(y) if how == "relative" else p - y


def search(x: np.ndarray, y: np.ndarray, names: list[str], max_c: int = 12, seed: int = 0,
           seconds: float = 60.0, heldout: int = 0) -> dict:
    t0 = time.time()
    if len(y) < MIN_ROWS:
        raise ValueError(f"at least {MIN_ROWS} training rows")
    order = np.random.default_rng(seed).permutation(len(y))
    folds = [f for f in np.array_split(order, FOLDS) if len(f)]
    scored, stopped = [], False

    def score(law: dict) -> None:
        r = cv(x, y, law, folds)
        c = fit(x, y, law) if r is not None else None
        if r is None or c is None:
            return
        law = {**law, "c": c}
        law["complexity"] = complexity(law)
        law["cv_rmse"], law["cv_se"] = r
        law["train_rmse"] = rmse(predict(x, law, c), y)
        scored.append(law)

    for law in candidates(x, y, max_c):
        if time.time() - t0 > seconds:
            stopped = True
            break
        score(law)
    best1 = sorted((s for s in scored if len(s["terms"]) == 1 and not s.get("baseline")),
                   key=lambda s: s["cv_rmse"])[:TOP_SINGLES]
    for a, b in itertools.combinations(best1, 2):            # pairs: c0 + c1·g1 + c2·g2
        if time.time() - t0 > seconds:
            stopped = True
            break
        if a["kind"] != "lin" or b["kind"] != "lin" or a["terms"] == b["terms"]:
            continue
        law = {"kind": "lin", "intercept": True, "terms": [a["terms"][0], b["terms"][0]]}
        if complexity({**law, "c": [0.0] * 3}) <= max_c:
            score(law)
    if not scored:
        raise ValueError("no law could be fitted on these rows")
    best = min(scored, key=lambda s: s["cv_rmse"])
    near = [s for s in scored if s["cv_rmse"] <= best["cv_rmse"] + best["cv_se"]]
    chosen = min(near, key=lambda s: (s["complexity"], s["cv_rmse"]))
    how = "absolute"
    if heldout:                                              # D1's metric and bound, from the law's own residuals
        oof: list = []
        cv(x, y, chosen, folds, oof)
        how = metric(oof)
        r = np.asarray(oof, dtype=float)
        e = errors(r[:, 1] + r[:, 0], r[:, 1], how)
        chosen = {**chosen, "metric": how, "cv_error": rmse(e, np.zeros(len(e))), "d1_bound": bound(e.tolist(), heldout, seed)}
    front, low = [], math.inf
    for s in sorted(scored, key=lambda s: (s["complexity"], s["cv_rmse"])):
        if s["cv_rmse"] < low * (1 - 1e-9):
            front.append(s)
            low = s["cv_rmse"]
    base = baselines(x, y, scored, how)
    keep = lambda s: {k: s[k] for k in ("kind", "intercept", "terms", "c", "complexity", "cv_rmse", "cv_se",  # noqa: E731
                                        "train_rmse", "sign", "name", "baseline", "from", "d1_bound", "metric",
                                        "cv_error", "fit") if k in s}
    return {"chosen": {**keep(chosen), "text": text(chosen, names)},
            "front": [{**keep(s), "text": text(s, names)} for s in front],
            "baselines": {k: {**keep(v), "text": text(v, names)} for k, v in base.items()},
            "tried": len(scored), "stopped": stopped, "seconds": round(time.time() - t0, 2)}


# ---- the law in words (for people; never evaluated) --------------------------------------------------------------
def _num(v: float) -> str:
    return f"{v:.4g}"


def _exp(p: float) -> str:
    for d in (1, 2, 3, 6):
        if abs(p * d - round(p * d)) < 1e-9:
            return str(int(round(p))) if d == 1 else f"{int(round(p * d))}/{d}"
    return _num(p)


def _factor(f: dict, names: list[str]) -> str:
    n = names[f["v"]] if f["v"] < len(names) else f"x{f['v']}"
    if f["op"] == "pow":
        return n if f["p"] == 1.0 else f"{n}^({_exp(f['p'])})"
    return f"{f['op']}({n})"


def text(law: dict, names: list[str]) -> str:
    c = list(law.get("c") or [])
    parts = []
    if law["intercept"]:
        parts.append(_num(c.pop(0)) if c else "c0")
    for t in law["terms"]:
        coef = _num(c.pop(0)) if c else "c"
        parts.append(f"{coef}·" + "·".join(_factor(f, names) for f in t))
    body = " + ".join(parts).replace("+ -", "- ") or "0"
    if law["kind"] == "exp":
        return f"{'-' if law.get('sign', 1.0) < 0 else ''}exp({body})"
    return body


def main(payload: dict) -> dict:
    x = np.asarray(payload["x"], dtype=float)
    y = np.asarray(payload["y"], dtype=float)
    with np.errstate(all="ignore"):              # overflowing or undefined candidates are dropped, not reported
            return search(x, y, list(payload["names"]), int(payload.get("max_complexity", 12)),
                      int(payload.get("seed", 0)), float(payload.get("seconds", 60)), int(payload.get("heldout", 0)))
