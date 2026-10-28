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
    assert b > a and events[1]["parent"] == a and events[0]["payload"]["goal"].startswith("aurseal1:")   # N64
    assert sys_log.open_record(cfg, events[0], None)["payload"] == {"goal": "test"}


def test_a_chat_s_words_are_sealed_in_the_trace_and_open_for_their_user_only(cfg):
    """N64 phase 4: an invented question, answer, thought and search query never in plaintext on disk; the run's
    record opens them for the run's user and shows nothing of it to another user; the pieces of a draft not written."""
    from aurora import sys_context, sys_logread
    with sys_context.acting_as("giulia"):
        sys_log.trace("api", "run.start", {"question": "Quanto pesa il criceto Pellegrino Zuffo?"}, run_id="r9")
        sys_log.trace("api", "synthesis.delta", {"kind": "answer", "text": "Pellegrino Zuffo pesa"}, run_id="r9")
        sys_log.trace("api", "answer.final", {"text": "Pellegrino Zuffo pesa 120 grammi.", "abstained": False,
                                              "mode": "knowledge", "seconds": 2.5, "sources": []}, run_id="r9")
        sys_log.trace("agent", "agent.thought", {"text": "Zuffo vive in una gabbia blu"}, run_id="r9")
        sys_log.trace("agent", "tool.call", {"name": "web.search", "arguments": '{"q": "criceto Zuffo"}',
                                             "effect": "read"}, run_id="r9")
        sys_log.trace("search", "retrieval.hits", {"question": "peso criceto Zuffo", "candidates": 3, "hits": []},
                      run_id="r9")
    on_disk = "".join(f.read_text(encoding="utf-8") for f in (cfg.path("AURORA_LOG_DIR") / "trace").glob("*.jsonl"))
    assert "Zuffo" not in on_disk and "gabbia" not in on_disk and "synthesis.delta" not in on_disk
    assert '"mode": "knowledge"' in on_disk and '"seconds": 2.5' in on_disk and '"effect": "read"' in on_disk
    mine = sys_logread.run_events("r9", cfg, viewer="giulia")
    assert [e["event"] for e in mine] == ["run.start", "answer.final", "agent.thought", "tool.call", "retrieval.hits"]
    assert mine[0]["payload"]["question"] == "Quanto pesa il criceto Pellegrino Zuffo?"
    assert mine[1]["payload"]["text"] == "Pellegrino Zuffo pesa 120 grammi." and mine[1]["payload"]["sources"] == []
    assert mine[3]["payload"]["arguments"] == '{"q": "criceto Zuffo"}'
    assert sys_logread.run_events("r9", cfg, viewer="marco") == []
    assert sys_logread.answer_stats(1, cfg)["answers"] == 1        # the numbers stay plain for the statistics


def test_a_key_that_does_not_open_here_drops_the_words(cfg, monkeypatch):
    from aurora import sys_seal

    def locked(*a, **k):
        raise RuntimeError("locked")
    monkeypatch.setattr(sys_seal, "seal_text", locked)
    sys_log.trace("api", "run.start", {"question": "Il codice segreto di Ottavia"}, run_id="r8")
    line = (cfg.path("AURORA_LOG_DIR") / "trace" / "api.jsonl").read_text(encoding="utf-8")
    assert "Ottavia" not in line and "(not kept: " in line


def test_a_caged_plugin_logs_to_stderr_not_to_the_read_only_folder(cfg, monkeypatch, capsys):
    monkeypatch.setenv("AURORA_IN_SANDBOX", "1")
    sys_log.get_logger("caged_probe").info("pdf made")
    sys_log.trace("caged_probe", "made", {"n": 1})
    err = capsys.readouterr().err
    assert "INFO aurora.caged_probe pdf made" in err and '"event": "made"' in err
    assert not (cfg.path("AURORA_LOG_DIR") / "caged_probe").exists()


def test_a_loose_plugin_log_is_rotated_and_keeps_being_written(cfg):
    folder = cfg.path("AURORA_LOG_DIR") / "plugins"
    folder.mkdir(parents=True, exist_ok=True)
    live, small = folder / "github.stderr.log", folder / "web.stderr.log"
    big = cfg["AURORA_LOG_MAX_MB"] * sys_log.MIB + 10
    writer = open(live, "a", encoding="utf-8")            # the plugin host keeps it open in append mode
    writer.write("x" * big)
    writer.flush()
    small.write_text("short\n")
    rotated = sys_log.rotate_loose(cfg)
    assert [f.name.startswith("github.stderr.") and f.name.endswith(".log.gz") for f in rotated] == [True]
    assert live.stat().st_size == 0 and small.read_text() == "short\n"
    assert len(gzip.decompress(rotated[0].read_bytes())) == big
    writer.write("after\n")
    writer.close()
    assert live.read_text() == "after\n"                   # no hole of zeros: append mode writes at the new end


def test_the_music_model_s_log_is_rotated_by_aurora_too(cfg):
    """C452: song.log was left to a logrotate rule of this machine only (as the owner's account: refused after U6)."""
    live = cfg.path("AURORA_LOG_DIR") / "song.log"
    live.parent.mkdir(parents=True, exist_ok=True)
    live.write_text("y" * (cfg["AURORA_LOG_MAX_MB"] * sys_log.MIB + 10))
    rotated = sys_log.rotate_loose(cfg)
    assert [f.name.startswith("song.") and f.name.endswith(".log.gz") for f in rotated] == [True]
    assert live.stat().st_size == 0


def test_each_kind_of_log_keeps_its_own_days(cfg):
    """Roadmap 78: the firewall's syslog 90 days, the trace 30, everything else AURORA_LOG_RETENTION_DAYS (365)."""
    root = cfg.path("AURORA_LOG_DIR")
    past = time.time() - 60 * 86400                        # two months old: gone from trace/ only
    files = {k: root / k / f"{k}.20260101-000000.log.gz" for k in ("firewall", "trace", "api")}
    for f in files.values():
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"data")
        os.utime(f, (past, past))
    assert [sys_log.retention(cfg, root / k) for k in ("firewall", "trace", "api")] == [90, 30, 365]
    removed = sys_log.purge_all(cfg)
    assert removed == [files["trace"]] and files["firewall"].exists() and files["api"].exists()
