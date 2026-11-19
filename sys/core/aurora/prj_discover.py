# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔭 The discovery engine of the projects (ROADMAP N147; owner: «possiamo crearci un modello ai che da solo riscopra la
fisica»; decided: an own numpy search on CPU, the data a file of the project, the projects' ceilings).

discover(cfg, project, data, target) → a law found from a table and tested on rows it never saw:
  1. the table (a .csv with a header, or a .npz of 1-D arrays; read only, inside the project) is loaded here, rows with
     a missing or non-finite value dropped and counted; the rows are split train / held-out by a permutation whose seed
     is derived from the table's SHA-256 and the target (C620: a chosen seed let an agent shop for a lucky split);
  2. the split is frozen (prj_prereg, N142) BEFORE the search: the held-out rows' indices and their SHA-256;
  3. the search (prj_discover_search) runs in a cage with NO project folder (C619: a python the project put first on
     the PATH read every row), started with Aurora's own interpreter by its absolute path, no network, one
     thread, an address-space limit, at most AURORA_DISCOVER_TIMEOUT_S; it receives the TRAINING ROWS ONLY;
  4. the law it chooses is frozen as two predictions (and the SHA-256 of its exact structure) BEFORE the held-out rows
     are touched — D1 its held-out RMSE at most the 99th percentile of what as many rows reach when drawn from its own
     out-of-fold residuals (a calibration check), D2 below 0.9 × the BEST of the constant, the linear and the zero law
     on the same rows (C620: the caller chose the baseline, and the linear one overfits with several inputs), each
     fitted in the metric it is scored in (C687: absolute fits scored in relative error were a straw man);
  5. the held-out rows of a (table, target) are used ONCE: a second attempt is refused (C620); Aurora evaluates both
     laws on them (structures, never text), writes discover/NNN_<target>.json (exclusive create, a copy and its
     SHA-256 in the user's state) and closes both frozen entries (the split «void»: procedural, never a «passed»).
«DISCOVERED» means only: a formula of the grammar, frozen before it saw them, predicted the held-out rows ≥ 10 % better
than the better baseline, as well as its training residuals promised — not that the law is true. It is never said when
nothing was frozen, the ledger changed, the search stopped at its time limit, the table was written by Aurora's agent
(prj_provenance, by its bytes or its numbers: C632, C686 — a command or a write tool, in this phase or any earlier
one), its provenance cannot be told (C685), or the target was tried before on other tables (C640). Since C697/C698 the
provenance is positive: only a table whose bytes or numbers the owner brought in (an upload, a chat attachment
imported, a clone from the page: prj_provenance.record_owner) can be DISCOVERED; a table with no such row is
«PASSED, NOT CLAIMABLE», whoever wrote it. The output of a
frozen long run with intact code is the agent's own simulation: it passes as «PASSED ON THE AGENT'S OWN SIMULATION»,
never «DISCOVERED» (C686). The table is known by
its numbers (prj_discover_data.canonical), not its bytes. The last HISTORY results are kept in the user's state.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

from . import prj_discover_search as S
from . import prj_prereg, prj_run, sys_config
from . import sys_users_layout as L

NAME = "discover_law"
DIR = "discover"
from .prj_discover_data import MAX_BYTES, MAX_INPUTS, MAX_MEMBERS, MAX_ROWS  # noqa: E402,F401  (the tables' limits)
HISTORY = 50
D2_FACTOR = 0.9                  # below this × the best baseline's held-out RMSE
BASELINES = ("constant", "linear", "zero")   # C687: the law p = 0 too (relative error 1 everywhere)
MIN_HELDOUT, PER_INPUT = 20, 10  # held-out rows: at least max(20, 10 × inputs) (C620)
CAGE_MB = 3072                   # the search's address space (C620: the bootstrap had no bound)
ORIGIN = "discover"              # the ledger's mark of the engine's entries (prj_prereg: agents cannot close them)

TOOL = {"name": NAME, "description": "Find a law y = f(x) in a table of the project (.csv with a header, or .npz) and "
        "test it on rows it never saw: Aurora freezes the train / held-out split (fixed by the table), searches "
        "formulas on the training rows only (powers, log, exp, sin, cos, products, fitted constants; a cage), freezes "
        "the chosen law, then measures it on the held-out rows against the best of the constant, linear and zero laws. "
        "Each table and target can be tried once. DISCOVERED means only that the formula predicted unseen rows "
        "≥10 % better than every baseline, as its residuals promised; not that the law is true.",
        "inputSchema": {"type": "object", "properties": {
            "data": {"type": "string", "description": "the table, a .csv or .npz file in the project"},
            "target": {"type": "string", "description": "the column to explain (y)"},
            "inputs": {"type": "array", "items": {"type": "string"}, "description": "the columns to use (x); all "
                       "others when not given"},
            "holdout": {"type": "number", "description": "held-out share, 0.1 to 0.5"}},
            "required": ["data", "target"]}}
RULE = ("Laws found in data (Aurora's rule): call a law found in a table «discovered» only when discover_law says "
        "DISCOVERED, and say what that means: a formula frozen before it saw them predicted held-out rows ≥10 % better "
        "than the constant, linear and zero laws — evidence, not proof; otherwise say what it did not pass. Only data "
        "the owner brought in can be evidence: a table you wrote (any tool, any phase) never is; the output of your own "
        "long_run is your simulation: a law found in it describes your code, never call it discovered.")


def enabled(cfg: sys_config.Config) -> bool:
    return bool(cfg["AURORA_DISCOVER_ENABLED"])


def rule(cfg: sys_config.Config) -> str:
    return RULE if enabled(cfg) else ""


# ---- the table: prj_discover_data (here under the same names) ----------------------------------------------------
from .prj_discover_data import _file, _npz, canonical, load, table  # noqa: E402,F401


def seed_of(sha256: str, target: str) -> int:
    """The split's seed: fixed by the table and the target, never chosen (C620)."""
    return int(hashlib.sha256(f"{sha256}:{target}".encode()).hexdigest()[:8], 16)


def needed(k: int) -> int:
    return max(MIN_HELDOUT, PER_INPUT * k)


def split(n: int, seed: int, holdout: float, k: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """train, held-out indices: a permutation from the seed; ValueError when the held-out part is too small."""
    m = int(round(n * holdout))
    if m < needed(k):
        raise ValueError(f"{needed(k)} held-out rows needed for {k} input(s) (this table and share give {m}): more rows "
                         "or a larger holdout")
    order = np.random.default_rng(seed).permutation(n)
    return np.sort(order[m:]), np.sort(order[:m])


def _sha_rows(idx: np.ndarray) -> str:
    return hashlib.sha256(",".join(str(int(i)) for i in idx).encode()).hexdigest()


# ---- the search, in the cage -------------------------------------------------------------------------------------
def caged(cfg: sys_config.Config, root: Path, payload: dict, limit: float) -> dict:
    """prj_discover_search's source and the payload (base64 JSON: nothing to quote) to Aurora's own python, by its
    absolute path, in prj_run's read-only cage around an EMPTY folder (C619): no project file is reachable."""
    if not shutil.which("bwrap"):
        raise RuntimeError("bubblewrap (bwrap) is not installed: no cage, no search is run")
    blob = base64.b64encode(json.dumps(payload).encode()).decode()
    src = Path(S.__file__).read_text(encoding="utf-8")
    src += ("\nimport base64 as _b, json as _j\n_r = main(_j.loads(_b.b64decode('" + blob + "')))\n"
            "print('@@RESULT@@' + _j.dumps(_r))\n")
    with tempfile.TemporaryDirectory(prefix="aurora-discover-") as empty:
        cmd = f"ulimit -v {CAGE_MB * 1024} && exec {shlex.quote(sys.executable)} -I -"
        args = prj_run.cage(cfg, Path(empty), cmd, readonly=True)
        at = args.index("--chdir")
        args[at:at] = [a for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS") for a in ("--setenv", v, "1")]
        try:
            done = subprocess.run(args, input=src, capture_output=True, text=True, timeout=max(5, int(limit)))
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"stopped after {int(limit)} s (AURORA_DISCOVER_TIMEOUT_S)") from None
    line = next((ln for ln in reversed(done.stdout.splitlines()) if ln.startswith("@@RESULT@@")), "")
    if done.returncode != 0 or not line:
        tail = (done.stderr or done.stdout).strip().splitlines()[-1:] or [f"exit {done.returncode}"]
        raise RuntimeError(f"the search failed: {tail[0][:300]}")
    return json.loads(line[len("@@RESULT@@"):])


def direct(cfg: sys_config.Config, root: Path, payload: dict, limit: float) -> dict:
    """The same search in this process (the tests; never chosen by Aurora's own calls)."""
    return S.main(payload)


# ---- the experiment ----------------------------------------------------------------------------------------------
def _law(d: dict) -> dict:
    return {k: d[k] for k in ("kind", "intercept", "terms", "sign") if k in d}


def law_sha(d: dict) -> str:
    """The exact law frozen: its structure and constants (C621: the frozen text gave 4 figures)."""
    return hashlib.sha256(json.dumps({**_law(d), "c": d.get("c")}, sort_keys=True).encode()).hexdigest()


def heldout_rmse(x: np.ndarray, y: np.ndarray, d: dict, how: str = "absolute") -> float:
    """The law's error on rows: the RMSE of p − y, or of (p − y) / |y| when the search chose «relative»."""
    if how == "relative" and np.any(y == 0):
        return float("inf")
    with np.errstate(all="ignore"):
        p = S.predict(x, _law(d), d["c"])
        e = S.errors(p, y, how)
    return S.rmse(e, np.zeros(len(e))) if np.all(np.isfinite(e)) else float("inf")


def d1_bound(law: dict) -> float:
    """The held-out RMSE the law may reach (the search's bootstrap); without it, nothing passes."""
    return float(law.get("d1_bound", 0.0))


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "law"


def target_key(name: str) -> str:
    """A target's name as one key (C646: «Y» after «y» was a new target; C666: a lookalike «у» or «y_» was too): the
    title skeleton of prj_prereg — NFKC, format characters and accents dropped, lookalike letters mapped, case folded —
    letters and digits only."""
    from .prj_prereg import skeleton
    return "".join(c for c in skeleton(name) if c.isalnum()) or str(name or "").strip()


def _valid_project(cfg: sys_config.Config, project: str) -> bool:
    """C622: a name checked before anything is written in the user's state (a «../» wrote outside it)."""
    try:
        prj_run.project_dir(cfg, project)
        return True
    except ValueError:
        return False


def discover(cfg: sys_config.Config, project: str, data: str, target: str, inputs: list | None = None,
             holdout: float = 0.3, record: bool = True, runner=None, since: float | None = None) -> dict:
    """The verdict on one table (see the module's docstring). `runner`: the search's runner (caged by default);
    `since`: the run's start — a table written from then on is never evidence of a discovery (C620)."""
    t0 = time.time()
    r = {"status": "error", "errors": [], "data": str(data or ""), "target": str(target or ""), "law": "",
         "frozen": [], "seconds": 0.0}
    try:
        r.update(_discover(cfg, project, data, target, inputs, float(holdout or 0.3), runner or caged, since))
    except ValueError as e:
        r.update(status="refused", errors=[str(e)])
    except (RuntimeError, OSError) as e:
        r.update(status="error", errors=[str(e)])
    r["seconds"] = round(time.time() - t0, 1)
    r["created"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if record and enabled(cfg) and _valid_project(cfg, project):       # C622: never when off, never a bad name
        try:
            _keep(cfg, project, r)
        except (OSError, ValueError):
            pass
    return r


def _discover(cfg, project, data, target, inputs, holdout, runner, since) -> dict:
    if not enabled(cfg):
        raise RuntimeError("the discovery engine is off (AURORA_DISCOVER_ENABLED)")
    if not 0.1 <= holdout <= 0.5:
        raise ValueError("holdout: a share from 0.1 to 0.5")
    root = prj_run.project_dir(cfg, project).resolve()
    from . import prj_longrun                                 # C660: its tables may still change under the search
    if prj_longrun.busy(cfg, project):
        raise ValueError("a long run of the project is going: discovery waits until it ends and its outputs are hashed")
    t = table(root, data, target, inputs)
    n, k = len(t["y"]), len(t["names"])
    tnorm = target_key(t["target"])                         # C646: «y» and «Y», a lookalike letter: one target
    key = f"{t['canonical']}:{tnorm}"                       # C640: the numbers, not the bytes (a newline added)
    if (u := _used(cfg, project).get(key)):
        raise ValueError(f"the held-out rows of «{t['target']}» in {t['rel']} were used already ({u.get('created')}, "
                         f"{u.get('status')}): each table and target is tried once — new data are needed")
    seed = seed_of(t["canonical"], t["target"])
    tr, ho = split(n, seed, holdout, k)
    caveats = []
    if since is not None and max(t["mtime"], t["ctime"]) >= since:
        caveats.append("the table was written or changed in this run")
    from . import prj_longrun                                 # C660: a long run not finished may have written it
    lr = prj_longrun.unfinished_since(cfg, project)
    if lr is not None and t["ctime"] >= lr:
        caveats.append("the table changed while a long run of the project was going or not yet registered: its "
                       "outputs are the agent's until it ends and they are hashed")
    from . import prj_provenance                              # C632: who wrote it, by hash, whatever its date says;
    src = prj_provenance.origin(cfg, project, t["rel"], t["sha256"], t["canonical"])   # C686: and by its numbers
    how = src["why"]
    if not src["claimable"]:
        caveats.append(how)
    earlier = [u for u in _used(cfg, project).values() if u.get("target") == tnorm]   # C646: no window, refusals
    attempt = len(earlier) + 1                                # not counted (C640: other tables, same target)
    # C647: on a target tried before, only new data the owner brought (no agent wrote them) stay claimable; C686: the
    # output of the agent's own long run is not exempt
    if attempt > 1 and src["kind"] != "owner":
        caveats.append(f"attempt {attempt} on the target «{t['target']}» in this project (earlier: "
                       f"{', '.join(str(h.get('data')) for h in earlier[-3:])}): a target tried again on other "
                       "tables needs new data from a frozen experiment")
    freeze = prj_prereg.mode(cfg) != "off"
    out = {"data": t["rel"], "data_sha256": t["sha256"], "data_canonical_sha256": t["canonical"], "attempt": attempt,
           "provenance": how, "origin": src["kind"], "inputs": t["names"], "rows": n, "dropped": t["dropped"],
           "train_rows": int(len(tr)), "heldout_rows": int(len(ho)), "heldout_sha256": _sha_rows(ho), "seed": seed,
           "frozen": []}
    if freeze:                                               # 1. the split, before the search
        e = prj_prereg.freeze(cfg, project, f"Discovery split: {t['target']} from {t['rel']}", [
            {"id": "S1", "text": f"The search sees only the {len(tr)} training rows; the {len(ho)} held-out rows "
                                  f"(seed {seed} from the numbers' SHA-256, indices SHA-256 {out['heldout_sha256']}) "
                                  f"are used once, after the chosen law is frozen; attempt {attempt} on this target."}], [t["rel"]], origin=ORIGIN)
        out["frozen"].append(e["id"])
    limit = float(cfg["AURORA_DISCOVER_TIMEOUT_S"])
    payload = {"x": t["x"][tr].tolist(), "y": t["y"][tr].tolist(), "names": t["names"], "seed": seed,
               "max_complexity": int(cfg["AURORA_DISCOVER_MAX_COMPLEXITY"]), "heldout": int(len(ho)),
               "seconds": max(1.0, 0.7 * limit - 5)}         # the bootstrap and the start inside the limit (C620)
    found = runner(cfg, root, payload, limit)                # 2. the training rows only
    chosen, bases = found["chosen"], found["baselines"]
    how = chosen.get("metric", "absolute")
    out.update(law=chosen["text"], complexity=chosen["complexity"], cv_rmse=chosen["cv_rmse"], metric=how,
               baseline_laws={b: bases[b]["text"] for b in BASELINES if b in bases},
               tried=found["tried"], search_stopped=found["stopped"],
               front=[{f2: f[f2] for f2 in ("text", "complexity", "cv_rmse")} for f in found["front"]])
    if found["stopped"]:
        caveats.append("the search stopped at its time limit: the choice depended on the machine's speed")
    if chosen.get("baseline"):
        out["status"] = "nothing"
        out["why"] = f"no formula beat the {chosen.get('name', 'baseline')} law in cross-validation"
    preds = {}
    if out.get("status") != "nothing":                       # 3. the chosen law, frozen before the held-out rows
        out["law_sha256"] = law_sha(chosen)
        preds = {"D1": f"The law {chosen['text']} (exact structure SHA-256 {out['law_sha256']}) predicts the held-out "
                       f"rows with a {how} RMSE ≤ {d1_bound(chosen):.6g} (99th percentile of {len(ho)} rows drawn "
                       f"from its out-of-fold residuals; its cross-validated {how} RMSE "
                       f"{chosen.get('cv_error', chosen['cv_rmse']):.6g}).",
                 "D2": f"Its held-out {how} RMSE is below {D2_FACTOR} × the best ({how}) held-out RMSE of the "
                       f"baselines, each fitted in the {how} metric (C687): "
                       + ", ".join(f"the {b} law {bases[b]['text']}" for b in BASELINES if b in bases) + "."}
        if freeze:
            e = prj_prereg.freeze(cfg, project, f"Discovered law for {t['target']}",
                                  [{"id": k2, "text": v} for k2, v in preds.items()], [t["rel"]], origin=ORIGIN)
            out["frozen"].append(e["id"])
    _use(cfg, project, key, {**out, "target_key": tnorm})     # the held-out rows are spent from here on (C620)
    xh, yh = t["x"][ho], t["y"][ho]                          # 4. now, and only now, the held-out rows
    out["heldout_rmse"] = heldout_rmse(xh, yh, chosen, how)
    base_rmse = {b: heldout_rmse(xh, yh, bases[b], how) for b in BASELINES if b in bases}
    best = min(base_rmse, key=base_rmse.get)
    out.update(baseline=best, baseline_law=bases[best]["text"], baseline_heldout_rmse=base_rmse[best],
               baselines_heldout_rmse=base_rmse)
    other = "relative" if how == "absolute" else "absolute"   # the other metric, reported only (C621)
    out["other_metric"] = {"metric": other, "heldout_rmse": heldout_rmse(xh, yh, chosen, other),
                           "baselines": {b: heldout_rmse(xh, yh, bases[b], other) for b in BASELINES if b in bases}}
    ytr = t["y"][tr]
    tol = 1e-9 * (1.0 if how == "relative" else max(1.0, float(np.std(ytr))))   # exact to rounding: 0 ≤ 0
    d1_ok = out["heldout_rmse"] <= d1_bound(chosen) + tol
    d2_ok = out["heldout_rmse"] < D2_FACTOR * out["baseline_heldout_rmse"]
    if out.get("status") != "nothing":
        out["D1"], out["D2"] = ("passed" if d1_ok else "failed"), ("passed" if d2_ok else "failed")
    rel, sha = _report(cfg, project, root, t["target"], {**out, "caveats": caveats, "predictions": preds, "found": found})
    out["report"], out["report_sha256"] = rel, sha
    intact = True
    if freeze:                                               # 5. both entries closed with what was measured
        c = prj_prereg.close(cfg, project, out["frozen"][0], [{"id": "S1", "outcome": "void",
                             "value": f"procedural: {len(tr)} training rows sent to the search",
                             "note": f"report {rel} sha256 {sha}"}], t["rel"])
        intact = c["integrity"] == "intact"
        if len(out["frozen"]) > 1:
            c = prj_prereg.close(cfg, project, out["frozen"][1], [
                {"id": "D1", "outcome": out["D1"], "value": f"held-out RMSE {out['heldout_rmse']:.6g}",
                 "note": f"report {rel} sha256 {sha}"},
                {"id": "D2", "outcome": out["D2"], "value": f"better baseline ({best}) held-out RMSE "
                                                            f"{out['baseline_heldout_rmse']:.6g}"}], t["rel"])
            intact = intact and c["integrity"] == "intact"
    out["integrity"] = "intact" if intact else "changed after freeze"
    if not intact:
        caveats.append("a frozen file changed after the freeze")
    out["caveats"] = caveats
    if out.get("status") != "nothing":
        passed = d1_ok and d2_ok
        out["status"] = ("not_confirmed" if not passed else "passed_not_frozen" if not freeze
                         else "passed_not_claimable" if caveats
                         else "discovered" if src["kind"] == "owner"       # C697/C698: positive provenance only
                         else "passed_on_simulation" if src["kind"] == "simulation"   # C686
                         else "passed_not_claimable")
    return out


# ---- the user's state: held-out rows spent, the reports' copies, the history -------------------------------------
def _state(cfg: sys_config.Config, project: str) -> Path:
    if not prj_run.NAME.fullmatch(project or ""):
        raise ValueError("a project name")
    return L.place(cfg, "state", cfg.user) / "projects" / project


def _used(cfg: sys_config.Config, project: str) -> dict:
    try:
        d = json.loads((_state(cfg, project) / "discover_used.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _use(cfg: sys_config.Config, project: str, key: str, out: dict) -> None:
    d = _used(cfg, project)
    d[key] = {"created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "data": out["data"],
              "status": "law frozen" if out.get("law_sha256") else "nothing found", "frozen": list(out["frozen"]),
              "target": out.get("target_key", "")}
    f = _state(cfg, project) / "discover_used.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    tmp.replace(f)


def _report(cfg: sys_config.Config, project: str, root: Path, target: str, body: dict) -> tuple[str, str]:
    """discover/NNN_<target>.json, NNN after the highest one, created exclusively (C623: a count overwrote a file);
    its copy in the user's state, out of the cage's reach; returns the path and the SHA-256."""
    d = root / DIR
    d.mkdir(exist_ok=True)
    blob = json.dumps(body, ensure_ascii=False, indent=1, default=float).encode()
    nums = [int(m.group(1)) for f in d.iterdir() if (m := re.match(r"(\d+)_", f.name))]
    n = max(nums, default=0) + 1
    while True:
        rel = f"{DIR}/{n:03d}_{_slug(target)}.json"
        try:
            with (root / rel).open("xb") as fh:
                fh.write(blob)
            break
        except FileExistsError:
            n += 1
    copy = _state(cfg, project) / DIR / Path(rel).name
    copy.parent.mkdir(parents=True, exist_ok=True)
    copy.write_bytes(blob)
    return rel, hashlib.sha256(blob).hexdigest()


def _history_file(cfg: sys_config.Config, project: str) -> Path:
    return _state(cfg, project) / "discoveries.json"


def _keep(cfg: sys_config.Config, project: str, r: dict) -> None:
    f = _history_file(cfg, project)
    rows = history(cfg, project)
    rows.append({k: r.get(k) for k in ("created", "data", "target", "status", "origin", "law", "heldout_rmse",
                                       "baseline_heldout_rmse", "frozen", "report", "report_sha256", "caveats",
                                       "seconds", "errors")})
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(rows[-HISTORY:], ensure_ascii=False, default=float), encoding="utf-8")


def history(cfg: sys_config.Config, project: str) -> list[dict]:
    try:
        rows = json.loads(_history_file(cfg, project).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return rows if isinstance(rows, list) else []


MEANING = ("DISCOVERED means: a formula of the grammar, frozen before it saw them, predicted the held-out rows at "
           "least 10 % better than the constant, the linear and the zero law, as well as its training residuals promised. "
           "It is evidence, not a proof that the law is true.")


SIMULATED = ("Do not call this law discovered: the table is the output of your own simulation; the law shows what that "
             "code computes (the search recovered it), not something found in data from outside.")
SOURCES = {"owner": "brought in by the owner",
           "none": "no record that the owner brought it in (see «not claimable»)",
           "agent": "written by Aurora's agent (see «not claimable»)",
           "unknown": "who wrote it is not known (see «not claimable»)"}


def text(r: dict) -> str:
    """A result for a model: the status first, then the numbers behind it."""
    head = {"discovered": "DISCOVERED", "not_confirmed": "NOT CONFIRMED", "nothing": "NOTHING FOUND",
            "passed_not_frozen": "PASSED, NOT FROZEN", "passed_not_claimable": "PASSED, NOT CLAIMABLE",
            "passed_on_simulation": "PASSED ON THE AGENT'S OWN SIMULATION",
            "refused": "REFUSED", "error": "ERROR"}[r["status"]]
    out = [f"{head}: {r.get('target')} from {r.get('data')} ({r['seconds']} s)"]
    if r.get("law"):
        out.append(f"law: {r['law']} (complexity {r.get('complexity')}, cross-validated RMSE {r.get('cv_rmse', 0):.4g})")
    if "heldout_rmse" in r:
        out.append(f"held-out {r.get('metric')} RMSE {r['heldout_rmse']:.4g} vs the better baseline ({r.get('baseline')}) "
                   f"{r.get('baseline_law')}: {r['baseline_heldout_rmse']:.4g}; D1 {r.get('D1', '-')}, D2 {r.get('D2', '-')}")
    if r.get("origin"):                                     # C686: where the numbers came from, always said
        own = r["origin"] == "owner" and r.get("provenance")            # C697: the owner's row, said as it is
        out.append("data: " + (own or SOURCES.get(r["origin"]) or r.get("provenance") or r["origin"]))
    if r.get("why"):
        out.append(r["why"])
    if r.get("caveats"):
        out.append("not claimable: " + "; ".join(r["caveats"]))
    if r.get("frozen"):
        out.append(f"frozen entries: {', '.join(r['frozen'])}; report {r.get('report')}; ledger {r.get('integrity')}; "
                   "these held-out rows are now spent")
    out += r.get("errors") or []
    if r["status"] == "discovered":
        out.append(MEANING)
    elif r["status"] == "passed_on_simulation":
        out.append(SIMULATED)
    elif r["status"] not in ("refused", "error"):
        out.append("Do not call this law discovered.")
    return "\n".join(out)


def offered(cfg: sys_config.Config, goal: str) -> list[dict]:
    """The tool in the agent's form («project» added), offered in a project's phase when the engine is on."""
    if not enabled(cfg) or not any(w in (goal or "") for w in (NAME, "freeze_predictions")):
        return []
    s = json.loads(json.dumps(TOOL["inputSchema"]))
    s["properties"] = {"project": {"type": "string", "description": "the project's name"}, **s["properties"]}
    s["required"] = ["project", *s["required"]]
    return [{"name": NAME, "description": TOOL["description"], "input_schema": s}]


def run_args(a: dict) -> dict:
    """The tool's arguments (a seed or a baseline given is ignored: C620)."""
    return {"data": str(a.get("data", "")), "target": str(a.get("target", "")),
            "inputs": [str(x) for x in a.get("inputs") or []] or None, "holdout": float(a.get("holdout") or 0.3)}


def agent_call(agent, a: dict) -> str:
    if not enabled(agent.cfg):                        # C667: a tool never offered is not called either
        return "REFUSED: the discovery engine is off (AURORA_DISCOVER_ENABLED)"
    project = str(a.get("project") or a.get("name") or "")
    if not project:
        return f"ERROR: {NAME} needs «project» (the project's name), «data» and «target»."
    try:
        out = text(discover(agent.cfg, project, **run_args(a), since=getattr(agent, "started", None)))
    except (ValueError, TypeError, OSError) as e:
        return f"ERROR: {e}"
    if isinstance(getattr(agent, "projects", None), set):
        agent.projects.add(project)
    return out
