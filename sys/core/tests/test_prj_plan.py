# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A project carried by Aurora (ROADMAP 97): the step's command decides, three failures block, 🤝 waits."""
from types import SimpleNamespace

from aurora import prj_plan

STEPS = [{"title": "Scrivi i test", "test": "pytest -q tests"}, {"title": "Il parser", "test": "pytest -q tests/test_p.py"}]


def _plan(cfg, level=2, active=True):
    cfg.values["AURORA_PROJECT_AUTONOMY"] = level
    plan = prj_plan.create(cfg, "demo", "un parser", STEPS)
    plan["active"] = active
    return prj_plan.save(cfg, "demo", plan)


def test_a_step_is_done_only_when_its_command_passes(cfg):
    _plan(cfg)
    assert prj_plan.next_step(prj_plan.load(cfg, "demo")) == 0
    out = prj_plan.record(cfg, "demo", 0, {"exit": 1, "output": "1 failed"}, "r1", "fatto")   # the model said done
    assert out["event"] == "" and out["plan"]["steps"][0]["status"] == "open" and out["plan"]["steps"][0]["tries"] == 1
    out = prj_plan.record(cfg, "demo", 0, {"exit": 0, "output": "3 passed"}, "r2", "fatto")
    assert out["event"] == "project.step" and prj_plan.next_step(out["plan"]) == 1
    out = prj_plan.record(cfg, "demo", 1, {"exit": 0, "output": "ok"}, "r3", "fatto")
    assert out["event"] == "project.done" and not out["plan"]["active"] and prj_plan.next_step(out["plan"]) is None


def test_three_failures_block_the_step_and_the_plan_stops_there(cfg):
    _plan(cfg)
    for n in range(3):
        out = prj_plan.record(cfg, "demo", 0, {"exit": 2, "output": "error"}, f"r{n}", "")
    assert out["event"] == "project.blocked" and out["plan"]["steps"][0]["status"] == "blocked"
    assert prj_plan.next_step(out["plan"]) is None and prj_plan.due(cfg, ["demo"]) is None


def test_one_step_then_she_waits_for_the_owner(cfg):
    _plan(cfg, level=1)
    out = prj_plan.record(cfg, "demo", 0, {"exit": 0, "output": "ok"}, "r1", "")
    assert out["plan"]["waiting"] and prj_plan.next_step(out["plan"]) is None


def test_due_respects_the_level_the_pause_and_the_gap(cfg):
    _plan(cfg, level=0)
    assert prj_plan.due(cfg, ["demo"]) is None                       # 🔒 never by herself
    _plan(cfg, level=2, active=False)
    assert prj_plan.due(cfg, ["demo"]) is None                       # not started by the owner
    _plan(cfg, level=2)
    assert prj_plan.due(cfg, ["demo", "other"]) == "demo"
    prj_plan.record(cfg, "demo", 0, {"exit": 1, "output": ""}, "r1", "")
    assert prj_plan.due(cfg, ["demo"]) is None                       # just tried: the machine is not a farm
    assert prj_plan.due(cfg, ["demo"], now=prj_plan.time.time() + prj_plan.GAP_S + 1) == "demo"
    prj_plan.record(cfg, "demo", 0, {"exit": 0, "output": ""}, "r2", "")
    assert prj_plan.due(cfg, ["demo"]) == "demo"                     # a step done: the next one at once


def test_the_goal_tells_the_step_its_command_and_the_failed_attempts(cfg):
    _plan(cfg)
    prj_plan.record(cfg, "demo", 0, {"exit": 1, "output": "AssertionError: 2 != 3"}, "r1", "")
    g = prj_plan.goal_for(prj_plan.load(cfg, "demo"), "demo", 0)
    assert "step 1 of 2" in g and "`pytest -q tests`" in g and "AssertionError" in g and "write them first" in g


def test_the_model_s_draft_keeps_only_steps_with_a_command():
    llm = SimpleNamespace(complete=lambda *a, **k: SimpleNamespace(
        answer='Ecco: [{"title": "Test", "test": "pytest -q"}, {"title": "Senza comando"}, {"test": "x"}]'))
    assert [s["title"] for s in prj_plan.draft(llm, "un parser")] == ["Test"]


def test_the_daily_line_once_a_day_and_only_when_something_moved(cfg):
    _plan(cfg)
    assert prj_plan.daily_line(cfg, "demo") == ""
    prj_plan.record(cfg, "demo", 0, {"exit": 0, "output": ""}, "r1", "")
    line = prj_plan.daily_line(cfg, "demo")
    assert "1/2 passi" in line and prj_plan.daily_line(cfg, "demo") == ""
