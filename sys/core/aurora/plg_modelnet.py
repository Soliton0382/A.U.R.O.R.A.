# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A plugin's network that ends at Aurora's local model: "sandbox": {"network": "local"} (owner, 21 Oct: a tool
for a project may need the local model, never the internet).

The cage has no network at all (its own namespace, only its loopback); a unix socket carries the one service it
may reach. Outside, bridge() serves <status>/plugins/bridge/<pid>/llm.sock in Aurora's process and forwards it to
the local model's port; inside, the plugin runs under a small forwarder (standard library only, given with -c),
which listens on the cage's 127.0.0.1:<port> and forwards to the socket — the plugin's code talks to the model as
anywhere else, and nothing else of the machine or of the world answers it.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
from pathlib import Path

from . import sys_config

_served: dict[str, Path] = {}
_lock = threading.Lock()


def _pipe(a: socket.socket, b: socket.socket) -> None:
    try:
        while data := a.recv(65536):
            b.sendall(data)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def _join(client: socket.socket, connect) -> None:
    try:
        upstream = connect()
    except OSError:
        client.close()
        return
    threading.Thread(target=_pipe, args=(client, upstream), daemon=True).start()
    threading.Thread(target=_pipe, args=(upstream, client), daemon=True).start()


def _serve(listener: socket.socket, connect) -> None:
    while True:
        try:
            client, _ = listener.accept()
        except OSError:
            return
        _join(client, connect)


def bridge(cfg: sys_config.Config) -> tuple[Path, int]:
    """The socket of this process that reaches the local model, served from the first call on; and the port."""
    host, port = str(cfg["AURORA_LLM_HOST"]), int(cfg["AURORA_LLM_PORT"])
    d = cfg.path("AURORA_STATUS_DIR") / "plugins" / "bridge" / str(os.getpid())
    sock = d / "llm.sock"
    with _lock:
        if str(sock) not in _served:
            d.mkdir(parents=True, exist_ok=True)
            if sock.exists():
                sock.unlink()
            srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            srv.bind(str(sock))
            srv.listen(16)
            threading.Thread(target=_serve, args=(srv, lambda: socket.create_connection((host, port), timeout=10)),
                             daemon=True).start()
            _served[str(sock)] = sock
    return sock, port


# inside the cage, standard library only (the cage may not see Aurora's code): the cage's 127.0.0.1:<port> leads to
# the socket; then the plugin, with this process's stdio
_INSIDE = """
import socket, subprocess, sys, threading
sock, port, cmd = sys.argv[1], int(sys.argv[2]), sys.argv[4:]
def pipe(a, b):
    try:
        while True:
            d = a.recv(65536)
            if not d:
                break
            b.sendall(d)
    except OSError:
        pass
    for s in (a, b):
        try:
            s.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
def serve(srv):
    while True:
        c, _ = srv.accept()
        u = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            u.connect(sock)
        except OSError:
            c.close()
            continue
        threading.Thread(target=pipe, args=(c, u), daemon=True).start()
        threading.Thread(target=pipe, args=(u, c), daemon=True).start()
srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", port))
srv.listen(16)
threading.Thread(target=serve, args=(srv,), daemon=True).start()
sys.exit(subprocess.call(cmd))
"""


def wrap(cmd: list[str], sock: Path, port: int) -> list[str]:
    return [os.path.abspath(sys.executable), "-c", _INSIDE, str(sock), str(port), "--", *cmd]
