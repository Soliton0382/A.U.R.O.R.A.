# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""13 Nov: the routines' tick overlapped itself (aurora-rem's timeout sent the next while the first ran) and a home
command waited before its first model call, untimed. One tick at a time; the parts before the first call timed."""
import logging

from aurora import hom_auto, sys_log
from aurora.agt_loop import Agent

from test_agents import FakeHost, FakeLLM, call, fake_pipeline


def test_a_slow_automations_tick_says_its_parts(cfg, monkeypatch, caplog):
    clock = iter(range(0, 1000, 3))                               # every reading 3 s later
    monkeypatch.setattr("time.monotonic", lambda: next(clock))
    monkeypatch.setattr(hom_auto, "due", lambda c: [])
    monkeypatch.setattr(hom_auto, "load", lambda c: {"automations": []})
    log = logging.getLogger("test-auto")
    with caplog.at_level(logging.WARNING, logger="test-auto"):
        assert hom_auto.tick(cfg, "u", log) == []
    said = [r.getMessage() for r in caplog.records]
    assert len(said) == 1 and "home automations tick took" in said[0] and "due 3.0 s" in said[0] \
        and "load 3.0 s" in said[0]


def test_the_run_says_what_came_before_its_first_model_call(cfg, monkeypatch):
    seen = []
    monkeypatch.setattr(sys_log, "trace", lambda comp, event, payload, run_id=None, **k: seen.append((event, payload)))
    agent = Agent(fake_pipeline(FakeLLM([call("finish", summary="Fatto.")])), cfg)
    agent.host = FakeHost()
    agent.run("prova", lambda e, p: None, "run1")
    prepared = [p for e, p in seen if e == "agent.prepared"]
    assert len(prepared) == 1
    assert {"catalog", "policy", "asked", "model", "prompt", "fit", "total"} <= set(prepared[0])


def test_the_threads_photo_names_where_each_thread_is(cfg):
    import threading
    import time
    started, stop = threading.Event(), threading.Event()

    ns_busy: dict = {}                                            # a function "of Aurora's code" (its file name)
    exec(compile("def busy(started, stop, time):\n    started.set()\n    while not stop.is_set():\n"
                 "        time.sleep(0.01)\n", "/x/aurora/busy_module.py", "exec"), ns_busy)
    t = threading.Thread(target=ns_busy["busy"], args=(started, stop, time), name="busy-one", daemon=True)
    t.start()
    started.wait(2)
    try:
        import importlib.util
        spec = importlib.util.find_spec("aurora.api.routines")
        src = spec.loader.get_source("aurora.api.routines")
        ns: dict = {}
        exec(compile(src[src.index("def threads_photo"):src.index("@router.post(\"/v1/aurora/routines/tick\"")],
                     "routines.py", "exec"), {"threading": threading}, ns)
        photo = ns["threads_photo"](skip=threading.get_ident())
    finally:
        stop.set()
        t.join(2)
    assert "busy-one:" in photo


def test_a_plugin_scan_asks_the_signature_once_not_once_a_plugin(cfg, monkeypatch):
    """C600: 9,792 file stats a scan (the signature's stamp asked for each of 55 plugins) — once a scan now."""
    import json
    from aurora import plg_host, sys_ethics
    folder = cfg.path("AURORA_PLUGINS_DIR")
    for name in ("one", "two", "three"):
        (folder / name).mkdir(parents=True)
        (folder / name / "plugin.json").write_text(json.dumps({"name": name, "requires": []}))
    asked = []
    monkeypatch.setattr(sys_ethics, "unsigned_plugins", lambda root, *a: asked.append(1) or {"two"})
    monkeypatch.setattr(plg_host, "_REFUSED", set())
    out = {p.name: p.error for p in plg_host.PluginHost(cfg).plugins(with_tools=False)}
    assert len(asked) == 1
    assert out["one"] == "" and out["three"] == "" and "not signed" in out["two"]
