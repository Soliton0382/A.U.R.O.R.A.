# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🕶️ The anonymous chat (sys_anon): its turns sealed, never in clear on disk; emptied after 24 hours with its key, so an
old copy never opens again; a run in it writes no trace."""
import json
import time

from aurora import sys_anon, sys_context, sys_log


def test_the_turns_are_sealed_and_gone_with_their_key_after_24_hours(cfg):
    t0 = time.time()
    sys_anon.add(cfg, [{"role": "user", "text": "una domanda privata sul mio medico", "created_at": "x"},
                       {"role": "aurora", "text": "la risposta"}], now=t0)
    f = sys_anon._file(cfg, None)
    assert b"medico" not in f.read_bytes() and f.read_bytes().startswith(b"AURSEAL1")
    d = sys_anon.load(cfg, now=t0 + 3600)
    assert [x["role"] for x in d["turns"]] == ["user", "aurora"] and d["expires"] == t0 + 24 * 3600
    old = f.read_bytes()
    assert sys_anon.load(cfg, now=t0 + 24 * 3600 + 1)["turns"] == []                  # past its hours: emptied
    assert not f.exists() and not sys_anon._key(cfg, None).exists()                   # the key with it
    sys_anon.add(cfg, [{"role": "user", "text": "di nuovo"}])                         # a new file, a new key
    f.write_bytes(old)                                                                # the old copy put back
    assert sys_anon.load(cfg)["turns"] == []                                          # never opens


def test_cleared_at_once_and_a_run_in_it_writes_no_trace(cfg, tmp_path):
    sys_anon.add(cfg, [{"role": "user", "text": "ciao"}])
    assert sys_anon.clear(cfg) and sys_anon.load(cfg)["turns"] == []
    log = cfg.path("AURORA_LOG_DIR") / "trace" / "anontest.jsonl"
    sys_log.trace("anontest", "seen", {"q": "normale"})
    with sys_context.anonymous():
        sys_log.trace("anontest", "seen", {"q": "segreto"})
    lines = [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []
    assert [x["payload"]["q"] for x in lines] == ["normale"]


def test_in_the_anonymous_chat_she_only_reads(cfg):
    from types import SimpleNamespace
    host = SimpleNamespace(get=lambda p: SimpleNamespace(manifest={"outputs": {"make_pdf": {"pattern": "x"}}} if p == "docs" else {}))
    index = {"web__search": ("web", "search", "read"), "docs__make_pdf": ("docs", "make_pdf", "read"),
             "facebook__publish_post": ("facebook", "publish_post", "external")}
    assert sys_anon.refusal("create_artifact", index, host) == ""                     # not anonymous: nothing refused
    with sys_context.anonymous():
        assert sys_anon.refusal("web__search", index, host) == ""
        for name in ("docs__make_pdf", "facebook__publish_post", "create_artifact", "create_picture", "home_scene"):
            assert sys_anon.refusal(name, index, host).startswith("REFUSED")
