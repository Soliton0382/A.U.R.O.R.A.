# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's SSH keys sealed at rest (C463, ROADMAP N69 e: the firewall's console key and the power-off key were
private keys in clear, one of them 660): the file holds the key sealed with Aurora's key (sys_seal), its public half
beside it in clear (<key>.pub); each use opens it in memory into an ssh-agent of its own, alive for that call only, and
ssh is pointed at the agent and the public half — the private key is never on disk in clear again.

Linux only: the Mac and Windows ports keep their key file as it is (no private agent socket there)."""
from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import sys_config, sys_seal

PURPOSE = "sshkey"


def _here() -> bool:
    return sys.platform.startswith("linux") and bool(shutil.which("ssh-agent")) and bool(shutil.which("ssh-add"))


def seal_in_place(cfg: sys_config.Config, key: Path) -> bool:
    """A key in clear sealed where it is (its .pub made first when missing); True when it is sealed now."""
    blob = key.read_bytes()
    if blob.startswith(sys_seal.MAGIC):
        return True
    if not _here():
        return False
    pub = key.with_name(key.name + ".pub")
    if not pub.exists():
        # from its stdin: a file found 660 (the power key's) is refused by ssh-keygen as «unprotected»
        r = subprocess.run(["ssh-keygen", "-y", "-f", "/dev/stdin"], input=blob, capture_output=True, timeout=30)
        if r.returncode:
            raise RuntimeError(f"no public half for {key.name}: {r.stderr.decode(errors='replace').strip()[:200]}")
        pub.write_bytes(r.stdout)
    sys_seal.write(cfg, key, blob, None, PURPOSE)          # 600, the content sealed, replaced in one move
    return True


@contextlib.contextmanager
def ssh_options(cfg: sys_config.Config, key: Path):
    """The options that give ssh this key: an agent of its own holding it, opened in memory, for this call only (or the
    file itself, on a port, or a key still in clear that cannot be sealed here)."""
    if not seal_in_place(cfg, key):
        yield ["-i", str(key)]
        return
    plain = sys_seal.read(cfg, key, None, PURPOSE)
    box = Path(tempfile.mkdtemp(prefix="aurora-agent-"))      # 700: the socket nobody else may reach
    sock = box / "agent.sock"
    agent = subprocess.Popen(["ssh-agent", "-D", "-a", str(sock)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            if sock.exists():
                break
            time.sleep(0.05)
        env = {**os.environ, "SSH_AUTH_SOCK": str(sock)}
        r = subprocess.run(["ssh-add", "-q", "-"], input=plain, env=env, capture_output=True, timeout=15)
        if r.returncode:
            raise RuntimeError(f"the key {key.name} did not load into its agent: {r.stderr.decode(errors='replace')[:200]}")
        yield ["-o", f"IdentityAgent={sock}", "-i", str(key.with_name(key.name + ".pub"))]
    finally:
        del plain
        agent.kill()
        agent.wait(timeout=10)
        shutil.rmtree(box, ignore_errors=True)
