# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📊 The usage counts (sys_usage): a trace event counted live under its user, Aurora's own work under "", only names
and numbers kept (never a question or an argument), the history rebuilt from the trace files, a purged user's counts
gone."""
import json
import time

from aurora import sys_context, sys_log
from aurora import sys_usage as U

SECRET = "una domanda privata"


def work(user=None):
    with sys_context.acting_as(user):
        sys_log.trace("api", "run.start", {"question": SECRET})
        sys_log.trace("api", "run.end", {"seconds": 4.0})
        sys_log.trace("llm_client", "cloud.call", {"provider": "anthropic", "model": "m1",
                                                   "usage": {"input_tokens": 100, "output_tokens": 20}})
        sys_log.trace("llm_client", "local.call", {"role": "route", "tokens_out": 3, "seconds": 0.5, "chars_in": 900})
        sys_log.trace("plugins", "plugin.call", {"plugin": "weather", "tool": "now", "ok": False, "seconds": 1.0})
        sys_log.trace("agent", "tool.result", {"name": "weather__now", "text": SECRET})        # not counted


def test_counts_live_per_user_and_names_only(cfg):
    work("anna")
    work("anna")
    work()                                                        # Aurora on her own
    day = json.loads((U._dir(cfg) / f"{time.strftime('%Y%m%d')}.json").read_text())
    assert set(day) == {"anna", ""} and SECRET not in json.dumps(day)
    r = U.report(cfg, 1)
    s = r["totals"]
    assert (s["questions"], s["question_s"], s["cloud_calls"], s["cloud_tokens"]) == (3, 12.0, 3, 360)
    assert (s["local_calls"], s["tool_calls"], s["tool_failed"]) == (3, 3, 3)
    assert r["cloud"] == [{"name": "anthropic/m1", "calls": 3, "tokens": 360}]
    assert r["tools"][0]["name"] == "weather.now" and [u["user"] for u in r["users"]] == ["anna", ""]
    mine = U.report(cfg, 7, {"anna"})
    assert mine["totals"]["questions"] == 2 and [u["user"] for u in mine["users"]] == ["anna"] and len(mine["days"]) == 7


def test_the_history_from_the_trace_files(cfg):
    work("bea")
    f = U._dir(cfg) / f"{time.strftime('%Y%m%d')}.json"
    live = json.loads(f.read_text())
    f.unlink()
    assert U.rebuild(cfg) == {time.strftime("%Y%m%d"): 5}
    assert json.loads(f.read_text()) == live
    assert U.rebuild(cfg) == {}                                    # a day with its file is left as it is


def test_a_purged_user_leaves_no_counts(cfg):
    from aurora import sys_users_layout as L
    work("carla")
    work("dario")
    plan = [s for s in L.purge_plan(cfg, "carla") if s["what"] == "usage"]
    assert len(plan) == 1
    U.forget(U._dir(cfg) / f"{time.strftime('%Y%m%d')}.json", "carla")
    assert U.days_of(cfg, "carla") == [] and U.names(cfg) == {"dario"}
