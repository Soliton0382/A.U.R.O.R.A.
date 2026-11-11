# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C567: with the CA check off, the firewall's certificate is learnt at the owner's «Collega» and held at every call —
another certificate fails the handshake before the request (and its password) is sent."""
from __future__ import annotations

import datetime
import socket
import ssl
import threading

import httpx
import pytest

from aurora import sec_tlspin as T


def _cert(tmp_path, name):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "firewall.local")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=400))
            .not_valid_after(now - datetime.timedelta(days=1))            # expired, as firewalls' own often are
            .sign(key, hashes.SHA256()))
    c, k = tmp_path / f"{name}.crt", tmp_path / f"{name}.key"
    c.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    k.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption()))
    return c, k


class Server:
    """A tiny HTTPS server on loopback whose certificate can be swapped; it records what reached it."""
    def __init__(self, tmp_path):
        self.tmp, self.got = tmp_path, []
        self.sock = socket.create_server(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.use("a")
        threading.Thread(target=self._serve, daemon=True).start()

    def use(self, name):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(*_cert(self.tmp, name))
        self.ctx = ctx

    def _serve(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            try:
                with self.ctx.wrap_socket(conn, server_side=True) as s:
                    data = s.recv(65536)
                    if data:
                        self.got.append(data)
                        s.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")
            except (OSError, ssl.SSLError):
                pass


@pytest.fixture()
def server(tmp_path, real_tls):
    s = Server(tmp_path)
    yield s
    s.sock.close()


def test_the_certificate_learnt_is_held_and_another_one_never_gets_the_request(cfg, server):
    url = f"https://127.0.0.1:{server.port}"
    assert T.learn(cfg, url)
    r = httpx.post(url + "/api", data={"password": "secret-of-the-firewall"}, verify=T.verify(cfg, url, False))
    assert r.text == "ok" and server.got[-1].startswith(b"POST /api")        # expired, its own: still accepted
    server.use("b")                                                            # someone in the middle
    n = len(server.got)
    with pytest.raises(httpx.HTTPError) as e:
        httpx.post(url + "/api", data={"password": "secret-of-the-firewall"}, verify=T.verify(cfg, url, False))
    assert len(server.got) == n                                                # nothing of the request reached it
    assert "not the one confirmed" in T.why(e.value)
    T.learn(cfg, url)                                                          # the owner connects it again
    assert httpx.get(url, verify=T.verify(cfg, url, False)).text == "ok"


def test_with_the_ca_check_on_nothing_is_pinned(cfg, server):
    url = f"https://127.0.0.1:{server.port}"
    assert T.verify(cfg, url, True) is True and T.verify(cfg, "http://10.0.0.1", False) is True
    assert not T._file(cfg).exists()


def test_a_firewall_connected_before_is_pinned_at_its_first_call(cfg, server):
    url = f"https://127.0.0.1:{server.port}"
    assert isinstance(T.verify(cfg, url, False), ssl.SSLContext)
    pin = T._pins(cfg)[f"127.0.0.1:{server.port}"]
    assert len(pin["sha256"]) == 64 and oct(T._file(cfg).stat().st_mode)[-3:] == "600"
