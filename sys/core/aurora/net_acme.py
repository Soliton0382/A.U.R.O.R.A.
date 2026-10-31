# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔏 An ACME client (RFC 8555) for the HTTPS certificate, with the DNS challenge only (owner, 1 Nov: «aggiungere un
plugin let's encrypt così da sostituire il mini PC… uso il rinnovo DNS e il provider è cloudflare»).

Written on what Aurora already has (cryptography, httpx): no new program or package, the same on every system. The
account key (EC P-256) is kept in <STATUS>/https/acme/account.key (600); the certificate's own key is RSA 2048, the
one every client and media server takes. One order: the names asked, a TXT record per name at _acme-challenge (a
name and its wildcard share one, two values), seen from the Internet before the authority is told to look, removed
afterwards whatever happened."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from pathlib import Path

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.x509.oid import NameOID

DIRECTORY = {"production": "https://acme-v02.api.letsencrypt.org/directory",
             "staging": "https://acme-staging-v02.api.letsencrypt.org/directory"}


class AcmeError(Exception):
    pass


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _int(n: int) -> str:
    return b64u(n.to_bytes(32, "big"))


def account_key(folder: Path) -> ec.EllipticCurvePrivateKey:
    f = folder / "account.key"
    if f.exists():
        return serialization.load_pem_private_key(f.read_bytes(), None)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = ec.generate_private_key(ec.SECP256R1())
    fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as h:
        h.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    return key


def jwk(key: ec.EllipticCurvePrivateKey) -> dict:
    n = key.public_key().public_numbers()
    return {"crv": "P-256", "kty": "EC", "x": _int(n.x), "y": _int(n.y)}


def thumbprint(key: ec.EllipticCurvePrivateKey) -> str:
    return b64u(hashlib.sha256(json.dumps(jwk(key), sort_keys=True, separators=(",", ":")).encode()).digest())


def challenge_value(token: str, key: ec.EllipticCurvePrivateKey) -> str:
    """The TXT value of a dns-01 challenge: the key authorization's SHA-256."""
    return b64u(hashlib.sha256(f"{token}.{thumbprint(key)}".encode()).digest())


def new_key_and_csr(names: list[str]) -> tuple[bytes, bytes]:
    """(the certificate's private key in PEM, the CSR in DER) for `names`, the first as the common name."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, names[0].lstrip("*."))]))
           .add_extension(x509.SubjectAlternativeName([x509.DNSName(n) for n in names]), critical=False)
           .sign(key, hashes.SHA256()))
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                            serialization.NoEncryption())
    return pem, csr.public_bytes(serialization.Encoding.DER)


class Client:
    def __init__(self, key: ec.EllipticCurvePrivateKey, directory: str, http: httpx.Client | None = None,
                 sleep=time.sleep):
        self.key, self.http, self.sleep = key, http or httpx.Client(timeout=30), sleep
        self.dir = self.http.get(directory).raise_for_status().json()
        self.kid: str | None = None
        self.nonce: str | None = None

    def _nonce(self) -> str:
        if self.nonce:
            n, self.nonce = self.nonce, None
            return n
        return self.http.head(self.dir["newNonce"]).headers["Replay-Nonce"]

    def _sign(self, url: str, payload) -> dict:
        prot = {"alg": "ES256", "nonce": self._nonce(), "url": url}
        prot.update({"kid": self.kid} if self.kid else {"jwk": jwk(self.key)})
        p64 = b64u(json.dumps(prot).encode())
        body = "" if payload is None else b64u(json.dumps(payload).encode())   # None: POST-as-GET
        r, s = decode_dss_signature(self.key.sign(f"{p64}.{body}".encode(), ec.ECDSA(hashes.SHA256())))
        return {"protected": p64, "payload": body, "signature": b64u(r.to_bytes(32, "big") + s.to_bytes(32, "big"))}

    def post(self, url: str, payload=None, accept: str = "application/json") -> httpx.Response:
        for attempt in range(3):
            r = self.http.post(url, json=self._sign(url, payload),
                               headers={"Content-Type": "application/jose+json", "Accept": accept})
            self.nonce = r.headers.get("Replay-Nonce")
            if r.status_code < 400:
                return r
            try:
                err = r.json()
            except ValueError:
                err = {"detail": r.text[:200]}
            if err.get("type", "").endswith(":badNonce") and attempt < 2:
                continue                                  # a used nonce: the next one
            raise AcmeError(f"{err.get('type', '').rsplit(':', 1)[-1] or r.status_code}: {err.get('detail', '')}")
        raise AcmeError("badNonce three times")

    def account(self, email: str = "") -> str:
        payload = {"termsOfServiceAgreed": True, **({"contact": [f"mailto:{email}"]} if email else {})}
        r = self.post(self.dir["newAccount"], payload)
        self.kid = r.headers["Location"]
        return self.kid

    def _poll(self, url: str, done=("valid",), fail=("invalid",), timeout: float = 180) -> dict:
        end = time.monotonic() + timeout
        while True:
            body = self.post(url).json()
            if body.get("status") in done:
                return body
            if body.get("status") in fail:
                why = [c.get("error", {}).get("detail") for c in body.get("challenges", []) if c.get("error")]
                raise AcmeError(f"{body.get('status')}: {'; '.join(w for w in why if w) or body.get('error', {}).get('detail', '')}")
            if time.monotonic() >= end:
                raise AcmeError(f"still {body.get('status')} after {timeout:.0f} s")
            self.sleep(3)

    def certificate(self, names: list[str], dns, wait_seen, log=lambda m: None) -> tuple[bytes, bytes]:
        """(fullchain PEM, private key PEM) for `names`; `dns`: add_txt/remove_txt, `wait_seen(name, values)`."""
        order_r = self.post(self.dir["newOrder"], {"identifiers": [{"type": "dns", "value": n} for n in names]})
        order, order_url = order_r.json(), order_r.headers["Location"]
        todo: list[tuple[str, str, str]] = []                     # (record name, value, challenge url)
        for a in order["authorizations"]:
            auth = self.post(a).json()
            if auth.get("status") == "valid":
                continue                                          # validated recently: nothing to show
            ch = next((c for c in auth["challenges"] if c["type"] == "dns-01"), None)
            if ch is None:
                raise AcmeError(f"no dns-01 challenge for {auth['identifier']['value']}")
            todo.append((f"_acme-challenge.{auth['identifier']['value']}", challenge_value(ch["token"], self.key), ch["url"]))
        refs = []
        try:
            for name, value, _ in todo:
                refs.append(dns.add_txt(name, value))
                log(f"TXT {name} written")
            for name in sorted({n for n, _, _ in todo}):
                if not wait_seen(name, {v for n, v, _ in todo if n == name}):
                    raise AcmeError(f"{name}: the TXT record is not seen from the Internet after 3 minutes")
            log("TXT records seen from the Internet")
            for _, _, url in todo:
                self.post(url, {})
            for a in order["authorizations"]:
                self._poll(a)
            log("names validated")
        finally:
            for ref in refs:
                try:
                    dns.remove_txt(ref)
                except Exception:  # noqa: BLE001 — a record left behind is harmless, the certificate is not lost for it
                    log(f"TXT record {ref} not removed")
        key_pem, csr = new_key_and_csr(names)
        self.post(order["finalize"], {"csr": b64u(csr)})
        done = self._poll(order_url, fail=("invalid",))
        chain = self.post(done["certificate"], accept="application/pem-certificate-chain").content
        return chain, key_pem
