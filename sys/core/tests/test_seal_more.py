# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N64, more of a user's status files sealed with the user's key: the routines, a project's conversation with its
conductor, its reports and its plan, the ideas, and an approval's title in the logs and the trace. For each one: the
file on disk holds none of a made-up value, its reader gives it back, and a file written before N64 (plaintext) still
reads. Every value here is invented."""
import json

from aurora import sys_seal

SECRET = "Zanzibar violetto 4417"


def _clean(path) -> bool:
    """None of the made-up value in the file's bytes."""
    return SECRET.encode() not in path.read_bytes() and b"Zanzibar" not in path.read_bytes()


def test_the_routines_are_sealed(cfg):
    from aurora import sys_routines as R
    from conftest import private
    r = R.create(cfg, {"kind": "agent", "goal": SECRET, "schedule": {"every": "hours", "hours": 2}})
    R.record(cfg, r["id"], f"rapporto: {SECRET}", True)
    f = R._file(cfg, "routines.json")
    assert _clean(f) and sys_seal.is_sealed(f.read_bytes()) and private(f)
    got = R.get(cfg, r["id"])
    assert got["goal"] == SECRET and got["title"] == SECRET and got["last_text"] == f"rapporto: {SECRET}"
    f.write_text(json.dumps([{**r, "id": "old1", "goal": "di prima"}]))           # a file of before
    assert R.get(cfg, "old1")["goal"] == "di prima"
    R.update(cfg, "old1", {"enabled": False})
    assert sys_seal.is_sealed(f.read_bytes()) and R.get(cfg, "old1")["enabled"] is False   # sealed at its next write


def test_the_other_small_files_of_the_routines_module_stay_as_they_were(cfg):
    from aurora import sys_routines as R
    R._save(cfg, "plugins_ready.json", ["weather"])
    f = R._file(cfg, "plugins_ready.json")
    assert json.loads(f.read_text()) == ["weather"] and R._load(cfg, "plugins_ready.json", []) == ["weather"]


def test_a_sealed_routines_file_that_does_not_open_is_never_saved_over(cfg):
    import pytest
    from aurora import sys_routines as R
    R.create(cfg, {"kind": "agent", "goal": SECRET, "schedule": {"every": "hours", "hours": 2}})
    f = R._file(cfg, "routines.json")
    blob = bytearray(f.read_bytes())
    blob[-1] ^= 1                                                                  # changed on disk
    f.write_bytes(bytes(blob))
    with pytest.raises(ValueError):
        R.all_routines(cfg)


def test_the_conductors_conversation_is_sealed(cfg):
    from aurora import prj_conduct
    e = prj_conduct.add(cfg, "orsa", "ask", SECRET)
    prj_conduct.add(cfg, "orsa", "goal", f"obiettivo: {SECRET}", status="draft")
    f = prj_conduct._file(cfg, "orsa")
    assert _clean(f) and all(sys_seal.is_sealed(x) for x in f.read_text().splitlines())
    assert [x["text"] for x in prj_conduct.history(cfg, "orsa")] == [SECRET, f"obiettivo: {SECRET}"]
    with f.open("a") as fh:                                                        # a line of before beside them
        fh.write(json.dumps({"id": "x", "t": 1.0, "kind": "reply", "text": "di prima"}) + "\n")
    assert prj_conduct.history(cfg, "orsa")[-1]["text"] == "di prima"
    assert prj_conduct.update(cfg, "orsa", e["id"], status="seen")["status"] == "seen"
    assert _clean(f) and all(sys_seal.is_sealed(x) for x in f.read_text().splitlines())     # all sealed again
    assert [x["text"] for x in prj_conduct.history(cfg, "orsa")] == [SECRET, f"obiettivo: {SECRET}", "di prima"]


def test_a_projects_reports_are_sealed(cfg):
    from aurora import prj_reports
    prj_reports.add(cfg, "orsa", {"run_id": "r1", "goal": SECRET, "summary": f"fatto: {SECRET}"})
    f = prj_reports._file(cfg, "orsa")
    assert _clean(f) and sys_seal.is_sealed(f.read_text().splitlines()[0])
    assert prj_reports.all_of(cfg, "orsa")[0]["summary"] == f"fatto: {SECRET}"
    with f.open("a") as fh:
        fh.write(json.dumps({"at": 2.0, "run_id": "r0", "goal": "di prima", "summary": "di prima"}) + "\n")
    assert [x["goal"] for x in prj_reports.all_of(cfg, "orsa")] == ["di prima", SECRET]      # the newest first


def test_a_projects_plan_is_sealed(cfg):
    from aurora import prj_plan
    from conftest import private
    plan = {"goal": SECRET, "active": False, "steps": [{"title": f"passo {SECRET}", "test": "true", "status": "open",
                                                         "tries": 0, "runs": []}]}
    prj_plan.save(cfg, "orsa", plan)
    f = prj_plan._file(cfg, "orsa")
    assert _clean(f) and sys_seal.is_sealed(f.read_bytes()) and private(f)
    got = prj_plan.load(cfg, "orsa")
    assert got["goal"] == SECRET and got["steps"][0]["title"] == f"passo {SECRET}"
    f.write_text(json.dumps({"goal": "di prima", "steps": []}))
    assert prj_plan.load(cfg, "orsa")["goal"] == "di prima"
    assert prj_plan.load(cfg, "nessuno") is None


def test_the_ideas_are_sealed(cfg):
    from aurora import sys_ideas
    from conftest import private
    it = sys_ideas.add(cfg, {"title": SECRET, "text": f"vorrei {SECRET}"})
    f = sys_ideas._file(cfg)
    assert _clean(f) and sys_seal.is_sealed(f.read_bytes()) and private(f)
    assert sys_ideas.listing(cfg)[0]["text"] == f"vorrei {SECRET}"
    f.write_text(json.dumps([{**it, "id": "old1", "title": "di prima"}]))
    assert sys_ideas.listing(cfg)[0]["title"] == "di prima"
    sys_ideas.update(cfg, "old1", {"state": "considered"})
    assert sys_seal.is_sealed(f.read_bytes()) and sys_ideas.listing(cfg)[0]["state"] == "considered"


def test_an_approvals_title_is_never_plain_in_the_logs(cfg):
    from aurora import sys_log
    from aurora.sys_approvals import Approvals
    a = Approvals(cfg)
    item = a.request("tool_call", "external", f"scrivere a {SECRET}", "perché", {}, {"plugin": "email"}, run_id="r1")
    a.record_auto(f"pubblicare {SECRET}", "perché", {"plugin": "social"}, "ok", run_id="r2")
    logs = [f for f in cfg.path("AURORA_LOG_DIR").rglob("*") if f.is_file()]
    assert logs and all(_clean(f) for f in logs)
    lines = [json.loads(x) for x in (cfg.path("AURORA_LOG_DIR") / "trace" / "approvals.jsonl").read_text().splitlines()]
    req = next(x for x in lines if x["event"] == "approval.request")
    assert req["payload"]["id"] == item["id"] and sys_seal.is_sealed(req["payload"]["title"])   # the id stays plain
    assert sys_log.open_record(cfg, req, None)["payload"]["title"] == f"scrivere a {SECRET}"


def test_a_write_that_cannot_seal_leaves_no_temporary_file(cfg, tmp_path, monkeypatch):
    """C460: a process without the key left an empty .tmp of its own account, which the services could not replace."""
    import pytest
    from aurora import sys_seal

    def no_key(*a, **k):
        raise PermissionError("no key here")
    monkeypatch.setattr(sys_seal, "seal", no_key)
    target = tmp_path / "state" / "mask_learned.json"
    with pytest.raises(PermissionError):
        sys_seal.write(cfg, target, b"{}", None, "state")
    assert not list(target.parent.glob("*.tmp")) if target.parent.exists() else True
