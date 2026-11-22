# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C718–C723, the frictions of the first live run of N142–N147: the conductor's draft asks no commit and the referee
counts none missing (C718); discover_law names the error in its metric and shows the fitted constants with their
figures (C719); one try per table and target said in the rule and the tool, every candidate input in one call, a
second call of the same run refused with how to do it (C720); Aurora's own reports are evidence for close_predictions
(C721); the web source says «no results» apart from a failure and why it failed, a plugin's tool found by its short
name (C722); a feature on in the settings but read off says it waits for the restart, the same 409 for the three
(C723). Invented tables and projects in tmp_path; no network, no CLI, no cage."""
import ast
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from aurora import agt_tools, kno_web, prj_conduct, prj_discover as D, prj_discover_search as S
from aurora import prj_longrun, prj_novelty as N, prj_prereg as P, prj_referee, sys_config

KEYS = ("AURORA_LONGRUN_ENABLED", "AURORA_DISCOVER_ENABLED", "AURORA_NOVELTY_ENABLED")


@pytest.fixture
def on(cfg):
    for k in KEYS:
        cfg.values[k] = True
    return cfg


@pytest.fixture
def proj(cfg):
    p = cfg.path("AURORA_PROJECTS_DIR") / "molle"
    (p / "dati").mkdir(parents=True)
    return p


def table(cfg, proj, name="molla.csv", n=120, seed=5):
    """An invented spring: the period T = 2π·√(m/k) with 1 % noise, k fixed, and a column of pure noise."""
    g = np.random.default_rng(seed)
    m = g.uniform(0.1, 3.0, n)
    z = g.normal(0, 1, n)
    t = 2 * np.pi * np.sqrt(m / 4.0) * (1 + g.normal(0, 0.01, n))
    (proj / "dati" / name).write_text("m,z,T\n" + "".join(f"{a:.10g},{b:.10g},{c:.10g}\n" for a, b, c in zip(m, z, t)),
                                      encoding="utf-8")
    from aurora import prj_provenance
    prj_provenance.record_owner(cfg, proj.name, proj, [f"dati/{name}"], "upload", "test")
    return f"dati/{name}"


# ---- C718 -----------------------------------------------------------------------------------------------------------
def test_c718_the_draft_never_asks_a_commit(cfg):
    text = prj_conduct.draft_system(cfg, "molle", "default")
    assert "to commit," not in text and "commit locally" not in text
    assert "Never ask the agent to commit" in text and "📦 Pubblica" in text


def test_c718_the_referee_counts_no_missing_commit():
    assert "Work not committed is never a defect" in prj_referee.PROMPT
    prj_referee.PROMPT.format(name="molle", lang="it")              # still a valid template


def test_c718_the_agent_s_run_tool_asks_no_commit():
    from aurora import agt_loop
    run = next(t for t in agt_loop.LOOP_TOOLS if t["name"] == "run_in_project")
    assert "then commit" not in run["description"] and "Never commit" in run["description"]


# ---- C719 -----------------------------------------------------------------------------------------------------------
def test_c719_a_fitted_constant_keeps_its_figures():
    law = {"kind": "lin", "intercept": False, "terms": [[{"v": 0, "op": "pow", "p": 0.5}]], "c": [2.00005]}
    assert S.text(law, ["L"]) == "2.0000·L^(1/2)"
    assert S.text({**law, "c": [1.625]}, ["L"]) == "1.6250·L^(1/2)"
    assert S.text({**law, "c": [123456.0]}, ["L"]).startswith("1.2346e+05")


def test_c719_the_error_is_named_in_its_metric():
    r = {"status": "discovered", "target": "T", "data": "dati/p.csv", "seconds": 0.2, "law": "2.0000·L^(1/2)",
         "complexity": 5, "metric": "relative", "cv_rmse": 0.04938, "cv_error": 0.0203, "constants": [2.00005]}
    out = D.text(r)
    assert "cross-validated relative error 0.0203" in out and "0.04938" not in out
    assert "fitted constants: 2.00005" in out
    ab = D.text({**r, "metric": "absolute", "cv_error": 0.0412})
    assert "cross-validated RMSE 0.0412" in ab and "relative" not in ab.split("\n")[1]


def test_c719_a_real_search_reports_its_constants(on, proj):
    rel = table(on, proj)
    r = D.discover(on, "molle", rel, "T", ["m"], runner=D.direct)
    assert r["constants"] and isinstance(r["constants"][0], float)
    out = D.text(r)
    assert "fitted constants: " in out and f"cross-validated {'relative error' if r['metric'] == 'relative' else 'RMSE'}" in out


# ---- C720 -----------------------------------------------------------------------------------------------------------
def test_c720_the_rule_and_the_tool_say_one_call_with_every_input():
    assert "single discover_law call" in D.RULE and "every candidate input" in D.RULE
    assert "ONE call" in D.TOOL["description"] and "each input alone" in D.TOOL["description"]


def test_c720_a_second_call_of_the_same_run_says_how(on, proj):
    rel = table(on, proj)
    since = time.time() - 1
    first = D.discover(on, "molle", rel, "T", ["z"], runner=D.direct, since=since)
    assert first["status"] != "refused", D.text(first)
    again = D.discover(on, "molle", rel, "T", ["m", "z"], runner=D.direct, since=since)
    assert again["status"] == "refused"
    why = again["errors"][0]
    assert "already tried in this run" in why and "['z']" in why and "ONE discover_law call" in why
    later = D.discover(on, "molle", rel, "T", ["m"], runner=D.direct, since=time.time() + 5)   # another run
    assert "used already" in later["errors"][0]


def test_c720_parallel_calls_spend_the_rows_once(on, proj):
    rel = table(on, proj)
    since = time.time() - 1
    got = []
    ts = [threading.Thread(target=lambda i=i: got.append(D.discover(on, "molle", rel, "T", [i], runner=D.direct,
                                                                    since=since))) for i in ("m", "z", "m")]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert sorted(r["status"] == "refused" for r in got) == [False, True, True]


def test_c720_several_inputs_try_each_alone():
    """With m and z given, laws of m alone are in the search: one call covers the subsets of one input."""
    g = np.random.default_rng(3)
    m, z = g.uniform(0.1, 3, 150), g.normal(0, 1, 150)
    y = 3.0 * m ** 2 * (1 + g.normal(0, 0.01, 150))
    out = S.search(np.column_stack([m, z]), y, ["m", "z"], seed=1)
    assert "m^(2)" in out["chosen"]["text"] and "z" not in out["chosen"]["text"]


# ---- C721 -----------------------------------------------------------------------------------------------------------
def test_c721_aurora_s_reports_are_evidence(on, proj):
    rel = table(on, proj)
    r = D.discover(on, "molle", rel, "T", ["m"], runner=D.direct)
    e = P.freeze(on, "molle", "Periodo della molla", [{"id": "P1", "text": "T cresce come la radice di m"}], [])
    out = P.tool(on, "molle", "close_predictions", {"id": e["id"], "evidence": r["report"],
                                                     "outcomes": [{"id": "P1", "outcome": "passed", "value": r["law"]}]})
    assert "integrity intact" in out, out
    assert P.entries(on, "molle")[-1]["evidence"] == r["report"]
    for d in ("reviews", "longrun", "novelty"):
        (proj / d).mkdir(exist_ok=True)
        (proj / d / "001.md").write_text("x\n", encoding="utf-8")
        e2 = P.freeze(on, "molle", f"Prova {d}", [{"id": "Q", "text": "una previsione"}], [])
        assert "integrity intact" in P.tool(on, "molle", "close_predictions", {
            "id": e2["id"], "evidence": f"{d}/001.md", "outcomes": [{"id": "Q", "outcome": "void"}]})


def test_c721_never_prereg_nor_a_missing_report(on, proj):
    e = P.freeze(on, "molle", "Una", [{"id": "P1", "text": "una previsione"}], [])
    for ev, why in ((e["file"], "not a code file"), ("discover/999_x.json", "no such file"),
                    ("discover/../../fuori.txt", "outside the project"), ("reviews/.git/x", "no such file")):
        out = P.tool(on, "molle", "close_predictions", {"id": e["id"], "evidence": ev,
                                                         "outcomes": [{"id": "P1", "outcome": "void"}]})
        assert out.startswith("REFUSED") or "ERROR" in out, (ev, out)


# ---- C722 -----------------------------------------------------------------------------------------------------------
def test_c722_no_results_is_an_answer_a_failure_says_why(monkeypatch):
    monkeypatch.setattr(kno_web, "search_why", lambda q, n: ([], ["auto: no results", "bing,yahoo: no results"]))
    assert N.web("pendulum period", 6, None) == []
    monkeypatch.setattr(kno_web, "search_why", lambda q, n: ([], ["auto: no results",
                                                                  "bing,yahoo: network (ConnectError: down)"]))
    with pytest.raises(RuntimeError, match="network"):
        N.web("pendulum period", 6, None)


def test_c722_each_engine_s_failure_has_its_kind(monkeypatch):
    import httpx
    import sys as _sys

    class DDGSException(Exception):
        pass

    class RatelimitException(Exception):
        pass

    seen = iter([DDGSException("No results found."), RatelimitException("202 Ratelimit"),
                 httpx.ConnectError("unreachable")])

    class DDGS:
        def text(self, *a, **k):
            raise next(seen)
    monkeypatch.setitem(_sys.modules, "ddgs", SimpleNamespace(DDGS=DDGS))
    monkeypatch.setattr(kno_web, "brave_key", lambda: "")
    monkeypatch.setattr(kno_web.time, "sleep", lambda s: None)
    found, why = kno_web.search_why("pendulum period", 6)
    assert found == [] and why[0].endswith("no results") and "rate limited" in why[1] and "network" in why[2]
    req = httpx.Request("GET", "https://api.example")
    bad = httpx.HTTPStatusError("x", request=req, response=httpx.Response(401, request=req))
    assert kno_web.why_failed(bad) == "key refused (HTTP 401)"
    assert kno_web.why_failed(ValueError("not json")).startswith("format")


def test_c722_a_plugin_tool_by_its_short_name():
    index = {"projects__project_tree": ("projects", "project_tree", "read"),
             "projects__project_read_file": ("projects", "project_read_file", "read"),
             "notes__read_file": ("notes", "read_file", "read")}
    assert agt_tools.full_name("project_tree", index, "__") == "projects__project_tree"
    assert agt_tools.full_name("search_vault", index, "__", {"search_vault"}) == "search_vault"
    assert agt_tools.full_name("read_file", {**index, "x__read_file": ("x", "read_file", "read")}, "__") == "read_file"
    msg = agt_tools.unknown("project__project_tree", index, "__")
    assert "did you mean projects__project_tree" in msg
    later = SimpleNamespace(name="github", tools=[{"name": "list_issues"}])
    assert "more_tools" in agt_tools.unknown("list_issues", index, "__", [later])


# ---- C723 -----------------------------------------------------------------------------------------------------------
def _set_in_env(cfg, key, value):
    f = Path(cfg.env_file)
    lines = [ln for ln in f.read_text(encoding="utf-8").splitlines() if not ln.startswith(key + "=")]
    f.write_text("\n".join(lines + [f"{key}={value}"]) + "\n", encoding="utf-8")


RESTART = "attivo dopo il riavvio di aurora-api"


def test_c723_off_and_on_after_the_restart(cfg, proj):
    for k in KEYS:
        cfg.values[k] = False
    assert "is off (AURORA_DISCOVER_ENABLED)" in D.off_said(cfg) and RESTART not in D.off_said(cfg)
    for k in KEYS:
        _set_in_env(cfg, k, "true")
    assert all(sys_config.on_after_restart(cfg, k) for k in KEYS)
    r = D.discover(cfg, "molle", "dati/x.csv", "T", runner=D.direct)
    assert r["status"] == "error" and RESTART in r["errors"][0]
    assert RESTART in D.agent_call(SimpleNamespace(cfg=cfg), {"project": "molle"})
    assert RESTART in N.check(cfg, "The period of a spring grows as the root of its mass", record=False)["errors"][0]
    assert RESTART in N.agent_call(SimpleNamespace(cfg=cfg), {"project": "molle", "claim": "x"})
    with pytest.raises(RuntimeError, match=RESTART):
        prj_longrun.start(cfg, "molle", "true", {}, "t")
    assert RESTART in prj_longrun.act(cfg, "molle", {"action": "list"})
    cfg.values["AURORA_DISCOVER_ENABLED"] = True                   # the process on: nothing to wait for
    assert not sys_config.on_after_restart(cfg, "AURORA_DISCOVER_ENABLED")


def test_c723_no_env_file_means_simply_off(cfg, monkeypatch):
    cfg.values["AURORA_NOVELTY_ENABLED"] = False
    monkeypatch.setattr(cfg, "env_file", Path("/nonexistent/.env"))
    assert N.off_said(cfg) == "the literature check is off (AURORA_NOVELTY_ENABLED)"


def test_c723_the_three_posts_answer_409_alike():
    src = (Path(__file__).resolve().parents[1] / "aurora" / "api" / "projects_conduct.py").read_text(encoding="utf-8")
    fns = {f.name: ast.unparse(f) for f in ast.walk(ast.parse(src)) if isinstance(f, ast.AsyncFunctionDef)}
    for fn, engine in (("discover_run", "prj_discover"), ("novelty_check", "prj_novelty"),
                       ("longrun_start", "prj_longrun")):
        assert f"in_thread(_on, {engine})" in fns[fn], fn     # the .env read off the event loop
    on_fn = next(f for f in ast.walk(ast.parse(src)) if isinstance(f, ast.FunctionDef) and f.name == "_on")
    assert "status_code=409" in ast.unparse(on_fn) and "off_said" in ast.unparse(on_fn)
