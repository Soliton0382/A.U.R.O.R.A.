# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C463 (ROADMAP N69 e): an SSH key sealed at rest, opened into an agent of its own for one call — a real login."""
import shutil
import socket
import subprocess
import sys
import time

import pytest

from aurora import sys_seal, sys_sshkey

SSHD = shutil.which("sshd") or "/usr/sbin/sshd"
needs = pytest.mark.skipif(not sys.platform.startswith("linux") or not shutil.which("ssh-agent")
                           or not shutil.which(SSHD), reason="ssh, ssh-agent and sshd needed")


def _port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@needs
def test_a_sealed_key_logs_in_through_its_own_agent(cfg, tmp_path):
    d = tmp_path / "ssh"
    d.mkdir(mode=0o700)
    for k in ("host", "user"):
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(d / k)], check=True)
    (d / "user.pub").unlink()                                  # a key without its public half, as the firewall's was
    pub = subprocess.run(["ssh-keygen", "-y", "-f", str(d / "user")], capture_output=True, text=True, check=True).stdout
    (d / "auth").write_text(pub)
    port = _port()
    (d / "conf").write_text(f"Port {port}\nListenAddress 127.0.0.1\nHostKey {d / 'host'}\nAuthorizedKeysFile {d / 'auth'}\n"
                            f"PasswordAuthentication no\nKbdInteractiveAuthentication no\nUsePAM no\n"
                            f"PidFile {d / 'pid'}\nStrictModes no\n")
    sshd = subprocess.Popen([SSHD, "-D", "-f", str(d / "conf"), "-E", str(d / "log")])
    try:
        for _ in range(50):
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    break
            time.sleep(0.1)
        clear = (d / "user").read_bytes()
        with sys_sshkey.ssh_options(cfg, d / "user") as opts:
            r = subprocess.run(["ssh", *opts, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
                                "-o", "StrictHostKeyChecking=no", "-o", f"UserKnownHostsFile={d / 'known'}",
                                "-p", str(port), "127.0.0.1", "echo", "ok"], capture_output=True, text=True, timeout=30)
            sock = opts[1].split("=", 1)[1]
        assert r.stdout.strip() == "ok", r.stderr
        blob = (d / "user").read_bytes()
        assert blob.startswith(sys_seal.MAGIC) and b"PRIVATE KEY" not in blob and blob != clear   # sealed at rest
        assert (d / "user.pub").read_text() == pub and opts[-1] == str(d / "user.pub")      # ssh sees the public half
        assert not __import__("os").path.exists(sock)                                             # the agent gone
    finally:
        sshd.kill()


def test_a_certificate_this_account_cannot_open_is_seen_c519(tmp_path):
    """C519: from a person's shell caddy cannot open the service's certificate (600): the syntax is checked without it."""
    import os
    from aurora import net_https
    cert, key = tmp_path / "fullchain.pem", tmp_path / "privkey.pem"
    cert.write_text("x")
    key.write_text("x")
    f = tmp_path / "Caddyfile"
    f.write_text(f':443 {{\n\ttls "{cert}" "{key}"\n}}\n')
    assert net_https._certs_closed(f) is False
    os.chmod(key, 0)
    try:
        assert net_https._certs_closed(f) is (os.geteuid() != 0)            # root opens anything
    finally:
        os.chmod(key, 0o600)
