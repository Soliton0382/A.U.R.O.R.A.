# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A plugin with "network": "local" reaches the local model and nothing else (plg_modelnet): another port of this
machine and the world stay unreachable. A real bubblewrap cage."""
import json
import shutil
import socket
import subprocess
import threading

import pytest

from aurora import plg_contract, plg_sandbox


def _cage_works() -> bool:
    return bool(shutil.which("bwrap")) and subprocess.run(["bwrap", "--ro-bind", "/", "/", "true"],
                                                          capture_output=True).returncode == 0


def _server(answer: bytes) -> int:
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(4)

    def run():
        while True:
            c, _ = srv.accept()
            c.recv(100)
            c.sendall(answer)
            c.close()
    threading.Thread(target=run, daemon=True).start()
    return srv.getsockname()[1]


@pytest.mark.skipif(not _cage_works(), reason="bubblewrap missing, or inside a cage (no nested namespaces)")
def test_the_local_network_is_the_model_and_nothing_else(cfg, tmp_path, monkeypatch):
    model, other = _server(b"model"), _server(b"other")
    monkeypatch.setitem(cfg.values, "AURORA_LLM_HOST", "127.0.0.1")
    monkeypatch.setitem(cfg.values, "AURORA_LLM_PORT", model)
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    env = tmp_path / "filtered.env"
    env.write_text("X=1\n")
    probe = ("import json, socket\nout = {}\n"
             "for name, addr in (('model', ('127.0.0.1', %d)), ('other', ('127.0.0.1', %d)), ('world', ('1.1.1.1', 443))):\n"
             "    try:\n        s = socket.create_connection(addr, timeout=3); s.sendall(b'hi'); out[name] = s.recv(10).decode()\n"
             "    except OSError as e:\n        out[name] = 'refused'\n"
             "print(json.dumps(out))") % (model, other)
    seen = {}
    for net in ("local", False):
        cmd = plg_sandbox.wrap(["python3", "-c", probe], plugin, {"sandbox": {"network": net}}, env, cfg)
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr[-1500:]
        seen[net] = json.loads(r.stdout.strip().splitlines()[-1])
    assert seen["local"] == {"model": "model", "other": "refused", "world": "refused"}
    assert seen[False] == {"model": "refused", "other": "refused", "world": "refused"}


def test_the_contract_knows_the_local_network():
    m = {"name": "x", "version": "1", "kind": "tool", "description": {"it": "a", "en": "a"}, "command": ["{python}"]}
    assert not [e for e in plg_contract.check({**m, "sandbox": {"network": "local"}}) if "network" in e]
    assert [e for e in plg_contract.check({**m, "sandbox": {"network": "lan"}}) if "network" in e]


def test_a_forged_plugin_gets_its_own_only_whatever_its_manifest_says(cfg, tmp_path):
    """9 Nov: the cage itself — at every start — gives a forged plugin no folder but the projects', no secret but its
    own, no network but its proxy, and not another plugin's way out."""
    import tempfile
    from aurora import plg_netproxy, plg_sandbox as S
    from pathlib import Path
    short = Path(tempfile.mkdtemp(prefix="aur"))                           # a unix socket's path: 108 bytes at most
    import pytest
    mp = pytest.MonkeyPatch()
    mp.setattr(plg_netproxy, "folder", lambda c: short)
    bridges = cfg.path("AURORA_STATUS_DIR") / "plugins" / "bridge"
    bridges.mkdir(parents=True, exist_ok=True)
    m = {"name": "sly", "forged": {"request": "r"}, "env_as": {"AURORA_API_KEY": "K", "AURORA_SLY_TOKEN": "T"},
         "sandbox": {"network": True, "write": ["AURORA_STATUS_DIR", "AURORA_PROJECTS_DIR"]}}
    assert S._declared(m) == {"AURORA_SLY_TOKEN"}
    env = tmp_path / "f.env"
    env.write_text("")
    args = S.wrap(["python", "server.py"], tmp_path, m, env, cfg)
    binds = [args[i + 1] for i, a in enumerate(args) if a == "--bind"]
    assert binds == [str(cfg.path("AURORA_PROJECTS_DIR"))]                 # never the status folder
    assert "--unshare-net" in args and "HTTPS_PROXY" in args               # no network of its own: the proxy only
    assert args.index("--tmpfs", args.index(str(bridges)) - 1) >= 0 and str(bridges) in args   # the others' hidden
    official = S.wrap(["python", "server.py"], tmp_path, {**m, "forged": None}, env, cfg)
    assert "--unshare-net" not in official and "HTTPS_PROXY" not in official   # an owner's plugin: as before
    mp.undo()


def test_the_proxy_lets_through_only_the_owners_places(cfg, monkeypatch):
    from aurora import plg_netproxy as N
    import socket
    addrs = {"ha.lan": "192.168.1.40", "api.example.org": "93.184.216.34", "sneaky.example.org": "10.0.0.5",
             "me.lan": "127.0.0.1"}
    monkeypatch.setattr(socket, "getaddrinfo", lambda h, p=None, **k: [(0, 0, 0, "", (addrs.get(h, "203.0.113.9"), p or 0))])
    owner = [("ha.lan", 8123), ("me.lan", int(cfg["AURORA_API_PORT"]))]
    assert N.decide("ha.lan", 8123, owner, ["example.org"], cfg) == ("192.168.1.40", "")        # the owner's, on the LAN
    assert N.decide("ha.lan", 22, owner, ["example.org"], cfg)[1]                               # another port: no
    assert N.decide("api.example.org", 443, owner, ["api.example.org"], cfg)[0] == "93.184.216.34"
    assert "not among" in N.decide("api.example.org", 443, owner, ["example.org"], cfg)[1]    # the exact name only
    assert "private" in N.decide("sneaky.example.org", 443, owner, ["sneaky.example.org"], cfg)[1]   # a public name, a LAN address
    assert "not among" in N.decide("evil.test", 443, owner, ["example.org"], cfg)[1]
    assert "Aurora's own" in N.decide("me.lan", int(cfg["AURORA_API_PORT"]), owner, [], cfg)[1]  # never her own API


@pytest.mark.skipif(not _cage_works(), reason="bubblewrap missing, or inside a cage (no nested namespaces)")
def test_a_forged_plugin_in_the_real_cage_reaches_the_owners_address_and_nothing_else(cfg, tmp_path, monkeypatch):
    """9 Nov, the cage itself: the address the owner set in its settings answers, another port of the same machine is
    refused by the proxy, and a connection without the proxy finds no network at all."""
    import tempfile
    from pathlib import Path
    from aurora import plg_netproxy
    ok, other = _server(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok"), _server(b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nother")
    short = Path(tempfile.mkdtemp(prefix="aur"))
    monkeypatch.setattr(plg_netproxy, "folder", lambda c: short)
    monkeypatch.setitem(cfg.raw, "AURORA_PROBE_URL", f"http://127.0.0.1:{ok}")
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    env = tmp_path / "filtered.env"
    env.write_text("X=1\n")
    probe = ("import json, socket, urllib.request, urllib.error\nout = {}\n"
             "for name, url in (('owner', 'http://127.0.0.1:%d/'), ('other', 'http://127.0.0.1:%d/')):\n"
             "    try:\n        out[name] = urllib.request.urlopen(url, timeout=10).read().decode()\n"
             "    except urllib.error.HTTPError as e:\n        out[name] = 'refused %%d' %% e.code\n"
             "    except OSError as e:\n        out[name] = 'error'\n"
             "try:\n    socket.create_connection(('127.0.0.1', %d), timeout=3); out['direct'] = 'open'\n"
             "except OSError:\n    out['direct'] = 'no network'\n"
             "print(json.dumps(out))") % (ok, other, ok)
    m = {"name": "probe", "forged": {"request": "r"}, "sandbox": {"network": True}}
    r = subprocess.run(plg_sandbox.wrap(["python3", "-c", probe], plugin, m, env, cfg), capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr[-1500:]
    assert json.loads(r.stdout.strip().splitlines()[-1]) == {"owner": "ok", "other": "refused 403", "direct": "no network"}
