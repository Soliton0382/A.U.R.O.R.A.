# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Add-ons (27 Nov): loaded only where installed (their root settings file), their routes, ticks and pages; Evidentia
is one — its Aurora side carries requests to its own service and keeps nothing of the archive."""
import json
from pathlib import Path

from aurora import sys_addons

ROOT = Path(__file__).resolve().parents[3]


def test_nothing_is_loaded_where_the_add_on_is_not_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(sys_addons, "ETC", tmp_path)
    assert sys_addons.installed() == [] and sys_addons.routers() == [] and sys_addons.ticks() == []
    assert sys_addons.listing() == []


def test_evidentia_installed_brings_its_routes_tick_and_pages(tmp_path, monkeypatch):
    monkeypatch.setattr(sys_addons, "ETC", tmp_path)
    (tmp_path / "evidentia.env").write_text("EVD_DATA_DIR=/x\n")
    assert sys_addons.installed() == ["evidentia"]
    assert sys_addons.listing() == [{"name": "evidentia", "entry": "/static/addons/evidentia/index.js"}]
    init = (ROOT / "sys" / "evidentia" / "addon" / "__init__.py").read_text(encoding="utf-8")
    assert "return [api_evidentia.router]" in init and "return [evd_worker.tick]" in init
    api = (ROOT / "sys" / "evidentia" / "addon" / "api_evidentia.py").read_text(encoding="utf-8")
    assert '@router.post("/v1/aurora/evidentia-ask"' in api and "dependencies=[Depends(admin_only)]" in api
    svc = (Path(__file__).resolve().parents[1] / "script" / "svc_api.py").read_text(encoding="utf-8")
    assert "_addons.routers()" in svc and 'app.mount(f"/static/addons/{_name}"' in svc


def test_the_add_on_holds_nothing_private_and_talks_only_to_its_socket():
    addon = ROOT / "sys" / "evidentia" / "addon"
    text = "\n".join(p.read_text(encoding="utf-8") for p in addon.rglob("*") if p.suffix in (".py", ".js", ".json", ".css"))
    for word in ("EFTA", "Scaricati", "/home/", "Epstein", "DOJ-OGR"):
        assert word not in text, word
    assert 'SOCK = "/var/lib/evidentia-api/evidentia.sock"' in (addon / "evd_worker.py").read_text(encoding="utf-8")


def test_the_public_plugin_runs_roots_copy_without_network_or_memory():
    m = json.loads((ROOT / "sys" / "plugins" / "evidentia" / "plugin.json").read_text(encoding="utf-8"))
    assert m["name"] == "evidentia" and m["memory"] is False and m["sandbox"]["network"] is False
    assert m["command"][-1] == "/usr/local/lib/aurora/sys/evidentia/script/svc_mcp.py"
    assert "/home/" not in json.dumps(m)


def test_the_chat_agent_of_evidentia_uses_only_its_tools_and_the_local_model():
    src = (ROOT / "sys" / "evidentia" / "addon" / "evd_chat.py").read_text(encoding="utf-8")
    assert "agent.allow = {PLUGIN}" in src and "agent.local_only = True" in src and "agent.loop_tools = set()" in src


def test_evidentia_runs_leave_nothing_in_aurora_s_traces_or_notices():
    for f in ("evd_chat.py", "evd_worker.py"):
        assert "agent.no_trace = True" in (ROOT / "sys" / "evidentia" / "addon" / f).read_text(encoding="utf-8")
    loop = (ROOT / "sys" / "core" / "aurora" / "agt_loop.py").read_text(encoding="utf-8")
    assert 'if not getattr(self, "no_trace", False):' in loop
    core = (ROOT / "sys" / "core" / "aurora" / "api" / "core.py").read_text(encoding="utf-8")
    assert '"evidentia": "🕵️"' in core


def test_evidentia_runs_hand_their_steps_to_the_case_trail_not_to_aurora():
    loop = (ROOT / "sys" / "core" / "aurora" / "agt_loop.py").read_text(encoding="utf-8")
    assert 'elif (sink := getattr(self, "audit_sink", None)) is not None:' in loop
    chat = (ROOT / "sys" / "evidentia" / "addon" / "evd_chat.py").read_text(encoding="utf-8")
    worker = (ROOT / "sys" / "evidentia" / "addon" / "evd_worker.py").read_text(encoding="utf-8")
    assert "agent.audit_sink = trail.append" in chat and "agent.audit_sink = trail.append" in worker
    assert 'hand_over(case_id, "chat"' in chat and 'f"/cases/{case}/trace"' in worker


def test_the_page_reads_and_verifies_a_case_trail_but_never_writes_it():
    api = (ROOT / "sys" / "evidentia" / "addon" / "api_evidentia.py").read_text(encoding="utf-8")
    assert "trace|trace/verify" in api and 'if "/trace" in path and method != "GET":' in api



def test_evidentia_s_health_lines_say_service_and_backup(monkeypatch, tmp_path):
    import importlib.util
    import json
    import time
    spec = importlib.util.spec_from_file_location("evd_addon_h", ROOT / "sys" / "evidentia" / "addon" / "__init__.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    monkeypatch.setattr(m, "SOCK", str(tmp_path / "none.sock"))
    monkeypatch.setattr(m, "STATUS", str(tmp_path / "backup.json"))
    lines = m.health(None)
    assert lines[0][1] == "warn" and lines[1][1] == "warn"            # service down, no backup yet
    (tmp_path / "none.sock").write_text("")                          # C752: a file left there is not a service
    assert m.health(None)[0][1] == "warn"
    import socket
    (tmp_path / "none.sock").unlink()
    srv = socket.socket(socket.AF_UNIX)
    srv.bind(str(tmp_path / "none.sock"))
    srv.listen(1)
    (tmp_path / "backup.json").write_text(json.dumps({"ok": True, "at": time.time() - 3600, "files": 12, "bytes": 2e9}))
    assert [l[1] for l in m.health(None)] == ["ok", "ok"]
    (tmp_path / "backup.json").write_text(json.dumps({"ok": True, "at": time.time() - 40 * 3600, "files": 12, "bytes": 2e9}))
    assert m.health(None)[1][1] == "warn"                            # older than 30 h
    src = (ROOT / "sys" / "core" / "aurora" / "sys_health.py").read_text(encoding="utf-8")
    assert 'getattr(sys_addons.module(name), "health"' in src
