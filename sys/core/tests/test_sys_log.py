# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import gzip
import json
import os
import time

from aurora import sys_config, sys_log
from conftest import write_env


def test_logger_writes_in_its_own_folder(cfg):
    sys_log.get_logger("harvester").info("hello")
    log = cfg.path("AURORA_LOG_DIR") / "harvester" / "harvester.log"
    line = log.read_text(encoding="utf-8").strip()
    assert line.endswith("INFO aurora.harvester hello")


def test_rotation_compresses_and_keeps_the_content(tmp_path):
    cfg = sys_config.load(write_env(tmp_path, AURORA_LOG_MAX_MB="1"), check_root=False)
    sys_log.configure(cfg)
    lg = sys_log.get_logger("busy")
    for i in range(12000):
        lg.info("line %06d %s", i, "x" * 80)
    folder = cfg.path("AURORA_LOG_DIR") / "busy"
    rotated = sorted(folder.glob("busy.*.log.gz"))
    assert rotated, "no rotated file"
    assert (folder / "busy.log").stat().st_size < 1024 * 1024
    with gzip.open(rotated[0], "rt", encoding="utf-8") as f:
        assert "line 000000" in f.readline()


def test_purge_removes_only_old_rotated_files(cfg):
    folder = cfg.path("AURORA_LOG_DIR") / "x"
    folder.mkdir(parents=True)
    old, new, live = folder / "x.1.log.gz", folder / "x.2.log.gz", folder / "x.log"
    for f in (old, new, live):
        f.write_bytes(b"data")
    past = time.time() - 400 * 86400
    os.utime(old, (past, past))
    os.utime(live, (past, past))
    removed = sys_log.purge(folder, 365)
    assert removed == [old]
    assert new.exists() and live.exists()


def test_trace_is_one_json_event_per_line(cfg):
    a = sys_log.trace("api", "run.start", {"goal": "test"}, run_id="r1")
    b = sys_log.trace("api", "run.end", {}, run_id="r1", parent=a)
    lines = (cfg.path("AURORA_LOG_DIR") / "trace" / "api.jsonl").read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in lines]
    assert [e["event"] for e in events] == ["run.start", "run.end"]
    assert b > a and events[1]["parent"] == a and events[0]["payload"] == {"goal": "test"}


def test_a_caged_plugin_logs_to_stderr_not_to_the_read_only_folder(cfg, monkeypatch, capsys):
    monkeypatch.setenv("AURORA_IN_SANDBOX", "1")
    sys_log.get_logger("caged_probe").info("pdf made")
    sys_log.trace("caged_probe", "made", {"n": 1})
    err = capsys.readouterr().err
    assert "INFO aurora.caged_probe pdf made" in err and '"event": "made"' in err
    assert not (cfg.path("AURORA_LOG_DIR") / "caged_probe").exists()
