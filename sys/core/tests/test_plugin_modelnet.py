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
