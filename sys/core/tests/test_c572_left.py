# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C572, what was left: every component's trace sealed like the chat's (its readers open it, a line of before still
reads), and a purged user's conductor sessions removed from the CLI's folders."""
import json
import time
from datetime import datetime

from aurora import kno_morning, mdl_cloud, mdl_router, sys_context, sys_log, sys_usage


def _lines(cfg, component):
    f = cfg.path("AURORA_LOG_DIR") / "trace" / f"{component}.jsonl"
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines()], f


def _old(component, event, payload, **more):
    """A line as written before C572: its payload in plaintext."""
    return json.dumps({"ts": datetime.now().astimezone().isoformat(timespec="milliseconds"), "seq": 1, "pid": 1,
                       "component": component, "event": event, "run_id": None, "parent": None, "payload": payload, **more})


def test_a_non_chat_trace_keeps_no_words_in_plaintext_and_its_numbers_stay(cfg):
    sys_log.trace("ingest", "import", {"source_id": "doc:referto-di-fiordaliso.pdf", "title": "Referto di Fiordaliso",
                                       "chunks": 12, "seconds": 1.5, "domain": "medicine"})
    rows, f = _lines(cfg, "ingest")
    raw = f.read_text(encoding="utf-8")
    assert "Fiordaliso" not in raw and "referto" not in raw
    p = rows[0]["payload"]
    assert p["chunks"] == 12 and p["seconds"] == 1.5 and p["domain"] == "medicine"      # the structure stays plain
    assert p["title"].startswith("aurseal1:") and p["source_id"].startswith("aurseal1:")
    back = sys_log.opened(cfg, rows[0])["payload"]
    assert back["title"] == "Referto di Fiordaliso" and back["source_id"] == "doc:referto-di-fiordaliso.pdf"
    old = json.loads(_old("ingest", "import", {"source_id": "doc:di-prima", "chunks": 3}))
    assert sys_log.opened(cfg, old) == old                           # a line of before reads as it is


def test_the_morning_counts_the_harvest_from_sealed_and_old_lines(cfg):
    sys_log.trace("harvester", "harvest.round", {"domains": [{"domain": "physics", "new": 2, "chunks": 30},
                                                               {"domain": "law", "new": 1, "chunks": 5}]})
    rows, f = _lines(cfg, "harvester")
    assert isinstance(rows[0]["payload"]["domains"], str)            # sealed on disk
    with open(f, "a", encoding="utf-8") as h:
        h.write(_old("harvester", "harvest.round", {"domains": [{"domain": "physics", "new": 4, "chunks": 40}]}) + "\n")
        h.write(_old("harvester", "harvest.round", {"domains": "(does not open)"}) + "\n")    # never a crash
    assert kno_morning._harvested(cfg, time.time() - 3600) == (7, 75)


def test_the_cloud_s_figures_read_sealed_and_old_lines(cfg):
    sys_log.trace("llm_client", "cloud.call", {"provider": "claude_code", "model": "opus", "cost_usd": 0.5, "seconds": 2,
                                               "usage": {"input_tokens": 10, "output_tokens": 4}})
    sys_log.trace("llm_client", "cloud.mask", {"role": "answer", "masked": {"EMAIL": 2, "PRIVATE": 1}, "images": 0})
    rows, f = _lines(cfg, "llm_client")
    assert isinstance(rows[1]["payload"]["masked"], str) and rows[0]["payload"]["usage"]["input_tokens"] == 10
    with open(f, "a", encoding="utf-8") as h:
        h.write(_old("llm_client", "cloud.mask", {"role": "answer", "masked": {"EMAIL": 1}, "images": 1}) + "\n")
    s = mdl_router.stats(cfg, 1)
    assert s["masked"] == {"EMAIL": 3, "PRIVATE": 1} and s["pictures_sent"] == 1 and s["masked_calls_by_role"] == {"answer": 2}
    assert s["calls"]["claude_code · opus"]["calls"] == 1 and s["calls"]["claude_code · opus"]["in"] == 10
    for day in sys_usage._dir(cfg).glob("*.json"):                   # the usage built again from the sealed traces
        day.unlink()
    assert sum(sys_usage.rebuild(cfg, force=True).values()) == 1


def test_an_anonymous_run_still_writes_nothing(cfg):
    with sys_context.anonymous():
        sys_log.trace("ingest", "import", {"title": "segreto"})
    assert not (cfg.path("AURORA_LOG_DIR") / "trace" / "ingest.jsonl").exists()


def test_a_purged_user_s_conductor_sessions_leave_the_cli_s_folders(cfg, monkeypatch, tmp_path):
    from aurora import sys_users_layout as L
    from aurora.sys_users import Users
    users = Users(cfg)
    users.add("boss", "admin", "password-di-prova-1")
    users.add("ospite", "user", "password-di-prova-2")
    users.add("ospite-due", "user", "password-di-prova-3")
    L.migrate(cfg, "boss")
    talk = cfg.path("AURORA_STATUS_DIR") / "claude_code" / "talk"
    shared = cfg.path("AURORA_STATUS_DIR") / "cloud_accounts" / "0123456789ab"
    home = tmp_path / "service-home"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home))
    kept = []
    for user in ("ospite", "ospite-due", "boss"):
        work = talk / user / "motore"
        work.mkdir(parents=True)
        for config in (shared, home):
            t = config / "projects" / mdl_cloud.cli_folder(work)
            t.mkdir(parents=True)
            (t / "session.jsonl").write_text('{"type":"user"}\n')
            kept.append((user, t))
    assert mdl_cloud.forget_user(cfg, "nobody") == 0
    out = L.purge(cfg, "ospite", "boss")
    assert out["accounts"] == 0
    assert not (talk / "ospite").exists() and (talk / "ospite-due" / "motore").is_dir()
    assert [u for u, t in kept if not t.exists()] == ["ospite", "ospite"]        # theirs only: not «ospite-due»'s
