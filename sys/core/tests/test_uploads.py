# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import os
import stat
import time

from aurora import sys_uploads as U


def test_files_are_kept_privately_and_found_by_their_turn(cfg):
    a = U.save(cfg, "run1", "../../etc/passwd", "image/jpeg", b"\xff\xd8 jpeg")
    b = U.save(cfg, "run1", "pagina.html", "text/html", b"<script>alert(1)</script>")
    c = U.save(cfg, "run2", "video.mp4", "video/mp4", b"mp4")
    path, item = U.get(cfg, a["id"])
    assert path.read_bytes() == b"\xff\xd8 jpeg" and item["name"] == "passwd" and "etc" not in str(path.relative_to(cfg.path("AURORA_UPLOADS_DIR")))
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    runs = U.by_run(cfg, {"run1"})
    assert [f["name"] for f in runs["run1"]] == ["passwd", "pagina.html"] and "run2" not in runs
    public = {f["name"]: f for f in U.all_uploads(cfg)}
    assert public["passwd"]["inline"] and public["video.mp4"]["inline"] and not public["pagina.html"]["inline"]
    assert "path" not in public["passwd"] and public["passwd"]["url"] == f"/v1/aurora/uploads/{a['id']}"
    assert U.total_bytes(cfg) == len(b"\xff\xd8 jpeg") + len(b"<script>alert(1)</script>") + 3
    assert U.delete(cfg, b["id"]) and U.get(cfg, b["id"]) is None and not U.delete(cfg, b["id"])
    assert U.get(cfg, c["id"]) is not None


def test_files_follow_their_conversation_and_the_age_limit(cfg):
    kept = U.save(cfg, "alive", "a.jpg", "image/jpeg", b"1")
    gone = U.save(cfg, "forgotten", "b.jpg", "image/jpeg", b"2")
    assert U.purge(cfg, {"alive"}) == []                               # its answer is still being written
    assert U.purge(cfg, {"alive"}, now=time.time() + 2 * 3600) == [gone["id"]]
    assert [f["id"] for f in U.all_uploads(cfg)] == [kept["id"]]
    assert U.purge(cfg, None) == []                                   # no age limit (0): kept
    cfg.values["AURORA_UPLOADS_KEEP_DAYS"] = 30
    assert U.purge(cfg, None, now=time.time() + 31 * 86400) == [kept["id"]]
    assert U.all_uploads(cfg) == []
    fresh = U.save(cfg, "x", "c.jpg", "image/jpeg", b"3")
    assert U.purge(cfg, set(), grace=0) == [fresh["id"]]                 # a memory reset leaves nothing behind
