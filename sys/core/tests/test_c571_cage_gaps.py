# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C571, the cage's smaller gaps (area audit, 10 Nov): the folders a plugin writes are bound before everything hidden,
a URL the manifest only proposes is never «the owner's address», a remote MCP server in the house must be said so and
is never Aurora's own service, and the bridges' folder loses the sockets of processes long gone. Invented addresses."""
import asyncio
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from aurora import plg_contract, plg_host, plg_mcp, plg_netproxy, plg_sandbox


def _cage_works() -> bool:
    return bool(shutil.which("bwrap")) and subprocess.run(["bwrap", "--ro-bind", "/", "/", "true"],
                                                          capture_output=True).returncode == 0


def _wrapped(cfg, tmp_path, manifest, cmd=("python3",)):
    env = tmp_path / "filtered.env"
    env.write_text("X=1\n")
    plugin = tmp_path / "plugin"
    plugin.mkdir(exist_ok=True)
    return plg_sandbox.wrap(list(cmd), plugin, manifest, env, cfg)


def test_the_folders_it_writes_are_bound_before_everything_hidden(cfg, tmp_path):
    status = cfg.path("AURORA_STATUS_DIR")
    for d in ("keys", "plugins/env"):
        (status / d).mkdir(parents=True, exist_ok=True)
    args = _wrapped(cfg, tmp_path, {"sandbox": {"write": ["AURORA_STATUS_DIR"]}})
    write = next(i for i, a in enumerate(args) if a == "--bind" and args[i + 1] == str(status))
    hidden = next(i for i, a in enumerate(args) if a == "--tmpfs" and args[i + 1] == str(status / "keys"))
    env = next(i for i, a in enumerate(args) if a == "--ro-bind" and args[i + 2] == str(cfg.env_file))
    run = next(i for i, a in enumerate(args) if a == "--tmpfs" and args[i + 1] == "/run")
    assert write < env < run and write < hidden
    later = [args[i + 1] for i in range(write + 1, len(args) - 1) if args[i] == "--tmpfs"]
    assert {str(status / "keys"), str(status / "plugins" / "env"), str(status / "plugins" / "bridge"), "/run"} <= set(later)


@pytest.mark.skipif(not _cage_works(), reason="bubblewrap missing, or inside a cage (no nested namespaces)")
def test_a_write_folder_above_a_hidden_one_does_not_show_it_again(cfg, tmp_path):
    status = cfg.path("AURORA_STATUS_DIR")
    (status / "keys").mkdir(parents=True, exist_ok=True)
    (status / "keys" / "machine.key").write_text("KEPT-OUT")
    (status / "note.txt").write_text("plain")
    probe = ("import os, sys\n"
             "print(open(sys.argv[1] + '/note.txt').read(), os.path.exists(sys.argv[1] + '/keys/machine.key'), "
             "os.access(sys.argv[1], os.W_OK))")
    r = subprocess.run(_wrapped(cfg, tmp_path, {"sandbox": {"write": ["AURORA_STATUS_DIR"]}},
                                ("python3", "-c", probe, str(status))), capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-1500:]
    assert r.stdout.split() == ["plain", "False", "True"]          # written there, the keys still hidden


def test_a_url_the_manifest_only_proposes_is_not_the_owners_address(cfg, monkeypatch):
    m = {"name": "probe", "forged": {"request": "r"}, "hosts": ["files.example.org"], "settings_spec": [
        {"key": "AURORA_PROBE_URL", "recommended": "http://192.168.1.1:8080/admin"},
        {"key": "AURORA_PROBE_FEED", "recommended": "https://api.example.org/v1"},
        {"key": "AURORA_API_KEY", "recommended": "https://core.example.org"}]}           # not its own setting
    monkeypatch.setitem(cfg.raw, "AURORA_PROBE_URL", "http://192.168.1.1:8080/admin")    # left as proposed: not typed
    monkeypatch.setitem(cfg.raw, "AURORA_PROBE_FEED", "https://api.example.org/v1")
    assert plg_netproxy.own_urls("probe", cfg, m) == []
    assert plg_netproxy.suggested_hosts(m) == ["api.example.org"]                         # a public name only
    monkeypatch.setitem(cfg.raw, "AURORA_PROBE_URL", "http://192.168.1.40:8123")         # the owner's own words
    assert plg_netproxy.own_urls("probe", cfg, m) == [("192.168.1.40", 8123)]
    assert plg_netproxy.own_urls("probe", cfg) == [("192.168.1.40", 8123), ("api.example.org", 443)]   # no manifest: as before


def test_the_bridge_serves_a_proposed_host_as_public_only(cfg, monkeypatch):
    seen = {}
    monkeypatch.setattr(plg_netproxy, "_serve", lambda srv, name, owner, public, c: seen.update(owner=owner, public=public))
    short = Path(tempfile.mkdtemp(prefix="aur"))
    monkeypatch.setattr(plg_netproxy, "folder", lambda c: short)
    m = {"name": "probe", "hosts": ["files.example.org"], "settings_spec": [
        {"key": "AURORA_PROBE_URL", "recommended": "http://192.168.1.1:8080/admin"},
        {"key": "AURORA_PROBE_FEED", "recommended": "https://api.example.org/v1"}]}
    monkeypatch.setitem(cfg.raw, "AURORA_PROBE_URL", "http://192.168.1.1:8080/admin")
    monkeypatch.setitem(cfg.raw, "AURORA_PROBE_FEED", "https://api.example.org/v1")
    try:
        plg_netproxy.bridge("probe", m, cfg)
        for _ in range(200):
            if seen:
                break
            import time
            time.sleep(0.01)
        assert seen == {"owner": [], "public": ["api.example.org", "files.example.org"]}
    finally:
        plg_netproxy._served.clear()
        shutil.rmtree(short, ignore_errors=True)


def test_the_proxy_never_reaches_a_link_local_or_reserved_address(cfg, monkeypatch):
    addrs = {"meta.lan": "169.254.169.254", "cast.lan": "224.0.0.251", "ha.lan": "192.168.1.40", "old.lan": "240.0.0.1"}
    monkeypatch.setattr(socket, "getaddrinfo", lambda h, p=None, **k: [(0, 0, 0, "", (addrs.get(h, "198.18.0.1"), p or 0))])
    owner = [(h, 80) for h in addrs]
    for host in ("meta.lan", "cast.lan", "old.lan"):
        assert "never reached" in plg_netproxy.decide(host, 80, owner, [], cfg)[1], host   # even typed by the owner
    assert plg_netproxy.decide("ha.lan", 80, owner, [], cfg) == ("192.168.1.40", "")       # the house stays his to type


def test_a_remote_mcp_server_in_the_house_must_be_said_so(cfg, monkeypatch):
    form = {"name": "archive", "description": "Searches the archive of public documents, with sources."}
    for url in ("http://10.0.0.5:8000/mcp", "http://127.0.0.1:8000/mcp", "http://localhost:8000/mcp", "http://[fd00::5]/mcp"):
        with pytest.raises(ValueError, match="private"):
            plg_mcp.manifest(cfg, {**form, "url": url})
    m = plg_mcp.manifest(cfg, {**form, "url": "http://10.0.0.5:8000/mcp", "lan": True})
    assert m["lan"] is True and plg_contract.check(m, "local_archive") == []
    assert "lan" not in plg_mcp.manifest(cfg, {**form, "url": "https://mcp.example.org/mcp"})   # a name: looked up at the call
    assert [e for e in plg_contract.check({**m, "url": "", "command": ["/bin/true"]}, "local_archive") if e.startswith("lan")]
    own = f"http://127.0.0.1:{int(cfg['AURORA_API_PORT'])}/mcp"
    for url, why in ((own, "Aurora's own"), ("http://169.254.169.254/mcp", "never reached")):   # not even «in the house»
        with pytest.raises(ValueError, match=why):
            plg_mcp.manifest(cfg, {**form, "url": url, "lan": True})


def test_a_name_is_looked_up_at_every_call(cfg, monkeypatch):
    addrs = {"mcp.example.org": "93.184.216.34", "moved.example.org": "192.168.1.1", "me.example.org": "127.0.0.1"}
    monkeypatch.setattr(socket, "getaddrinfo", lambda h, p=None, **k: [(0, 0, 0, "", (addrs.get(h, "198.18.0.1"), p or 0))])
    assert plg_mcp.address_problem("https://mcp.example.org/mcp", False, cfg) == ""
    assert "private" in plg_mcp.address_problem("https://moved.example.org/mcp", False, cfg)   # a public name, the house
    assert plg_mcp.address_problem("https://moved.example.org/mcp", True, cfg) == ""
    assert plg_mcp.address_problem("https://moved.example.org/mcp", False, cfg, resolve=False) == ""   # the form: no lookup
    api = int(cfg["AURORA_API_PORT"])
    assert "Aurora's own" in plg_mcp.address_problem(f"http://me.example.org:{api}/mcp", True, cfg)
    # the host refuses before any connection: the work is never started
    host = object.__new__(plg_host.PluginHost)
    host.cfg = cfg
    started = []

    async def work(session):
        started.append(session)
    p = SimpleNamespace(name="local_archive", manifest={"kind": "mcp", "url": "https://moved.example.org/mcp"})
    with pytest.raises(RuntimeError, match="not reached.*private"):
        asyncio.run(host._remote_session(p, work))
    assert started == []


def test_the_bridges_of_processes_long_gone_are_removed(monkeypatch):
    bridges = Path(tempfile.mkdtemp(prefix="aur"))                 # short: a unix socket's path has 108 bytes at most
    try:
        gone = []
        for _ in range(2):
            proc = subprocess.Popen(["true"])
            proc.wait()
            gone.append(str(proc.pid))
        import os
        dead, served, mine, other = bridges / gone[0], bridges / gone[1], bridges / str(os.getpid()), bridges / "notes"
        for d in (dead, served, mine, other):
            d.mkdir()
        stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)  # bound, closed, the file left: what a restart leaves
        stale.bind(str(dead / "llm.sock"))
        stale.close()
        live = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)   # another PID namespace's process: its socket answers
        live.bind(str(served / "llm.sock"))
        live.listen(1)
        (mine / "llm.sock").write_text("")
        monkeypatch.setattr(plg_sandbox, "_swept", set())
        plg_sandbox._sweep_bridges(bridges)
        assert not dead.exists() and served.is_dir() and mine.is_dir() and other.is_dir()
        live.close()
        plg_sandbox._sweep_bridges(bridges)                        # once per process: not at every plugin start
        assert served.is_dir()
        monkeypatch.setattr(plg_sandbox, "_swept", set())
        plg_sandbox._sweep_bridges(bridges)
        assert not served.exists() and mine.is_dir()
    finally:
        shutil.rmtree(bridges, ignore_errors=True)


def test_the_cage_sweeps_the_bridges_when_it_is_built(cfg, tmp_path, monkeypatch):
    proc = subprocess.Popen(["true"])
    proc.wait()
    dead = cfg.path("AURORA_STATUS_DIR") / "plugins" / "bridge" / str(proc.pid)
    dead.mkdir(parents=True)
    (dead / "n0123456789ab.sock").write_text("")
    monkeypatch.setattr(plg_sandbox, "_swept", set())
    _wrapped(cfg, tmp_path, {"sandbox": {"network": False}})
    assert not dead.exists()
