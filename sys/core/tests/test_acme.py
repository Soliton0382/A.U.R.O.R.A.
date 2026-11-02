# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔏 The certificate looked after by Aurora (owner, 1 Nov): the ACME client against a fake authority that really signs
the request, the DNS challenge through a fake Cloudflare, the certificate put in use, the copy for the NAS with
keyStore.p12 — no network."""
import base64
import datetime as dt
import json

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from aurora import net_acme, net_certs, net_dnsapi, net_https

D = "https://acme.test"


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _ca():
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Fake Authority")])
    now = dt.datetime.now(dt.UTC)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(1).not_valid_before(now).not_valid_after(now + dt.timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True).sign(key, hashes.SHA256()))
    return key, cert


class Authority:
    """A small ACME server: checks every JWS signature, asks the dns-01 TXT values, signs the CSR for 90 days."""

    def __init__(self, txt):
        self.ca_key, self.ca = _ca()
        self.txt, self.n, self.jwk, self.orders, self.seen_kid = txt, 0, None, {}, []

    def _ok(self, body=None, status=200, headers=None, content=None):
        h = {"Replay-Nonce": f"n{self.n}", **(headers or {})}
        self.n += 1
        return httpx.Response(status, json=body, headers=h) if content is None else httpx.Response(status, content=content, headers=h)

    def __call__(self, req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        if req.method == "GET" and url == D + "/dir":
            return httpx.Response(200, json={k: f"{D}/{k}" for k in ("newNonce", "newAccount", "newOrder")})
        if req.method == "HEAD":
            return self._ok()
        jws = json.loads(req.content)
        prot = json.loads(_unb64(jws["protected"]))
        assert prot["url"] == url and prot["alg"] == "ES256"
        key = prot.get("jwk") or self.jwk
        pub = ec.EllipticCurvePublicNumbers(int.from_bytes(_unb64(key["x"]), "big"), int.from_bytes(_unb64(key["y"]), "big"),
                                            ec.SECP256R1()).public_key()
        sig = _unb64(jws["signature"])
        pub.verify(encode_dss_signature(int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big")),
                   f"{jws['protected']}.{jws['payload']}".encode(), ec.ECDSA(hashes.SHA256()))
        payload = json.loads(_unb64(jws["payload"])) if jws["payload"] else None
        if url.endswith("/newAccount"):
            self.jwk = prot["jwk"]
            return self._ok({"status": "valid"}, 201, {"Location": f"{D}/acct/1"})
        self.seen_kid.append(prot.get("kid"))
        self.thumb = base64.urlsafe_b64encode(__import__("hashlib").sha256(json.dumps(self.jwk, sort_keys=True,
                                              separators=(",", ":")).encode()).digest()).rstrip(b"=").decode()
        if url.endswith("/newOrder"):
            names = [i["value"] for i in payload["identifiers"]]
            self.orders = {"names": names, "status": "pending", "authz": {f"{D}/authz/{i}": n for i, n in enumerate(names)},
                           "valid": set()}
            return self._ok({"status": "pending", "authorizations": list(self.orders["authz"]), "finalize": f"{D}/finalize"},
                            201, {"Location": f"{D}/order/1"})
        if "/authz/" in url:
            name = self.orders["authz"][url]
            base = name.removeprefix("*.")
            return self._ok({"status": "valid" if url in self.orders["valid"] else "pending",
                             "identifier": {"type": "dns", "value": base},
                             "challenges": [{"type": "http-01", "url": f"{D}/chall/h", "token": "x"},
                                            {"type": "dns-01", "url": f"{D}/chall/{url.rsplit('/', 1)[1]}", "token": f"tok{url[-1]}"}]})
        if "/chall/" in url:
            i = url.rsplit("/", 1)[1]
            authz = f"{D}/authz/{i}"
            base = self.orders["authz"][authz].removeprefix("*.")
            want = base64.urlsafe_b64encode(__import__("hashlib").sha256(f"tok{i}.{self.thumb}".encode()).digest()).rstrip(b"=").decode()
            assert want in self.txt.get(f"_acme-challenge.{base}", set()), "the TXT record is not there"
            self.orders["valid"].add(authz)
            return self._ok({"status": "valid"})
        if url.endswith("/finalize"):
            csr = x509.load_der_x509_csr(_unb64(payload["csr"]))
            san = csr.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
            assert sorted(san) == sorted(self.orders["names"])
            now = dt.datetime.now(dt.UTC)
            self.leaf = (x509.CertificateBuilder().subject_name(csr.subject).issuer_name(self.ca.subject)
                         .public_key(csr.public_key()).serial_number(2).not_valid_before(now)
                         .not_valid_after(now + dt.timedelta(days=90))
                         .add_extension(x509.SubjectAlternativeName([x509.DNSName(n) for n in san]), critical=False)
                         .sign(self.ca_key, hashes.SHA256()))
            self.orders["status"] = "valid"
            return self._ok({"status": "processing"})
        if url.endswith("/order/1"):
            return self._ok({"status": self.orders["status"], "certificate": f"{D}/cert/1"})
        if url.endswith("/cert/1"):
            pem = self.leaf.public_bytes(serialization.Encoding.PEM) + self.ca.public_bytes(serialization.Encoding.PEM)
            return self._ok(content=pem, headers={"Content-Type": "application/pem-certificate-chain"})
        raise AssertionError(f"unexpected {req.method} {url}")


class FakeDns:
    def __init__(self):
        self.txt, self.removed = {}, []

    def add_txt(self, name, value):
        self.txt.setdefault(name, set()).add(value)
        return f"{name}|{value}"

    def remove_txt(self, ref):
        name, value = ref.split("|")
        self.txt[name].discard(value)
        self.removed.append(ref)


def test_a_certificate_for_a_name_and_its_wildcard_through_the_dns_challenge(tmp_path):
    dns = FakeDns()
    auth = Authority(dns.txt)
    c = net_acme.Client(net_acme.account_key(tmp_path), D + "/dir", httpx.Client(transport=httpx.MockTransport(auth)),
                        sleep=lambda s: None)
    c.account("ada@example.org")
    seen = []
    chain, key = c.certificate(["example.org", "*.example.org"], dns, lambda n, v: seen.append((n, v)) or True)
    assert [n for n, _ in seen] == ["_acme-challenge.example.org"] and len(seen[0][1]) == 2   # one name, two values
    info = net_https.check_pair(chain, key, "example.org")
    assert sorted(info["names"]) == ["*.example.org", "example.org"] and info["issuer"] == "Fake Authority"
    assert not dns.txt["_acme-challenge.example.org"] and len(dns.removed) == 2              # removed afterwards
    assert set(auth.seen_kid) == {f"{D}/acct/1"}                                             # signed with the account
    assert (tmp_path / "account.key").stat().st_mode & 0o777 == 0o600


def test_the_txt_records_go_away_even_when_the_name_is_never_seen(tmp_path):
    dns = FakeDns()
    c = net_acme.Client(net_acme.account_key(tmp_path), D + "/dir",
                        httpx.Client(transport=httpx.MockTransport(Authority(dns.txt))), sleep=lambda s: None)
    c.account()
    with pytest.raises(net_acme.AcmeError, match="not seen"):
        c.certificate(["example.org"], dns, lambda n, v: False)
    assert dns.removed and not dns.txt["_acme-challenge.example.org"]


def test_cloudflare_finds_the_zone_and_writes_and_removes_the_record():
    calls = []

    def cf(req):
        calls.append((req.method, req.url.path, dict(req.url.params)))
        assert req.headers["Authorization"] == "Bearer tok"
        if req.url.path.endswith("/zones"):
            return httpx.Response(200, json={"success": True, "result": [{"id": "Z1"}] if req.url.params["name"] == "example.org" else []})
        if req.method == "POST":
            body = json.loads(req.content)
            assert body["type"] == "TXT" and body["name"] == "_acme-challenge.a.example.org"
            return httpx.Response(200, json={"success": True, "result": {"id": "R9"}})
        return httpx.Response(200, json={"success": True, "result": {}})
    d = net_dnsapi.Cloudflare("tok", httpx.Client(transport=httpx.MockTransport(cf)))
    ref = d.add_txt("_acme-challenge.a.example.org", "v")
    d.remove_txt(ref)
    assert ref == "Z1/R9" and calls[-1][:2] == ("DELETE", "/client/v4/zones/Z1/dns_records/R9")
    with pytest.raises(net_dnsapi.DnsError, match="token"):
        net_dnsapi.Cloudflare("")


@pytest.fixture
def https(cfg, tmp_path, monkeypatch):
    cfg.values.update(AURORA_TLS_CERT=str(tmp_path / "cert" / "fullchain.pem"), AURORA_TLS_KEY=str(tmp_path / "cert" / "privkey.pem"))
    monkeypatch.setattr(net_https, "fresh", lambda c: cfg)
    monkeypatch.setattr(net_https, "reload", lambda verb="reload": None)
    monkeypatch.setattr(net_https, "write", lambda c, **o: None)
    monkeypatch.setattr(net_https, "_settings", lambda c, ch: cfg.values.update(ch))
    cfg.values.update(AURORA_DOMAIN="example.org", AURORA_DOMAIN_ALIASES="", AURORA_TLS_MODE="internal",
                      AURORA_ACME_ENABLED=True, AURORA_ACME_DOMAINS="example.org, *.example.org", AURORA_ACME_EMAIL="",
                      AURORA_ACME_DNS="cloudflare", AURORA_ACME_DNS_TOKEN="tok", AURORA_ACME_STAGING=False,
                      AURORA_CERTS_COPY_DIR="", AURORA_CERTS_P12_PASSWORD="", AURORA_CERTS_P12_LEGACY=False,
                      AURORA_CERTS_COPY_NAMES="", AURORA_CERTS_P12=True)
    return cfg


def test_renewed_when_due_put_in_use_and_copied_for_the_nas(https, tmp_path, monkeypatch):
    dns = FakeDns()
    auth = Authority(dns.txt)
    monkeypatch.setattr(net_dnsapi, "provider", lambda cfg, client=None: dns)
    monkeypatch.setitem(net_acme.DIRECTORY, "production", D + "/dir")
    nas = tmp_path / "nas"
    nas.mkdir()
    https.values.update(AURORA_CERTS_COPY_DIR=str(nas), AURORA_CERTS_P12_PASSWORD="plex-pass")
    assert net_certs.why_due(https) == "no certificate of its own in use"
    r = net_certs.renew(https, http=httpx.Client(transport=httpx.MockTransport(auth)), wait_seen=lambda n, v: True)
    assert r["renewed"] and https["AURORA_TLS_MODE"] == "files" and net_certs.why_due(https) is None
    assert r["copied"]["copied"] and sorted(p.name for p in nas.iterdir()) == ["cert.pem", "chain.pem", "fullchain.pem",
                                                                              "keyStore.p12", "privkey.pem"]
    key, cert, more = pkcs12.load_key_and_certificates((nas / "keyStore.p12").read_bytes(), b"plex-pass")
    assert cert.subject.rfc4514_string() == "CN=example.org" and len(more) == 1
    assert net_certs.copy(https)["copied"] is False                             # the same: not written again
    https.values["AURORA_CERTS_P12_LEGACY"] = True
    (nas / "keyStore.p12").unlink()
    net_certs.copy(https)
    assert pkcs12.load_key_and_certificates((nas / "keyStore.p12").read_bytes(), b"plex-pass")[1] is not None
    st = net_certs.status(https)
    assert st["certificate"]["issuer"] == "Fake Authority" and st["renew_from"] and st["last"]["error"] is None
    assert any("validated" in s for s in st["last"]["steps"])


def test_a_failed_renewal_is_kept_for_the_page_and_the_old_certificate_stays(https, monkeypatch):
    def broken(cfg, client=None):
        raise net_dnsapi.DnsError("Cloudflare: Invalid API Token")
    monkeypatch.setattr(net_dnsapi, "provider", broken)
    with pytest.raises(net_certs.CertError, match="Invalid API Token"):
        net_certs.renew(https)
    assert net_certs.status(https)["last"]["error"].endswith("Invalid API Token") and https["AURORA_TLS_MODE"] == "internal"
    https.values["AURORA_ACME_ENABLED"] = False
    with pytest.raises(net_certs.CertError, match="off"):
        net_certs.renew(https, force=True)


def test_the_guided_way_by_hand_start_add_see_verify(https, tmp_path, monkeypatch):
    """1 Nov («metto il dominio, faccio partire, dà il token da aggiungere, lo aggiungo e poi fa la verifica»)."""
    zone: dict[str, set] = {}
    auth = Authority(zone)
    http = httpx.Client(transport=httpx.MockTransport(auth))
    monkeypatch.setitem(net_acme.DIRECTORY, "production", D + "/dir")
    monkeypatch.setattr(net_dnsapi, "txt", lambda name, client=None: zone.get(name, set()))
    https.values["AURORA_ACME_DNS"] = "manual"
    p = net_certs.start(https, http)
    assert p["manual"] and {r["name"] for r in p["records"]} == {"_acme-challenge.example.org"} and len(p["records"]) == 2
    assert net_certs.status(https)["pending"]["records"] == p["records"]
    assert not net_certs.check(https)["all_seen"]
    zone["_acme-challenge.example.org"] = {p["records"][0]["value"]}                 # one added: not yet
    assert [r["seen"] for r in net_certs.check(https)["records"]] == [True, False]
    zone["_acme-challenge.example.org"].add(p["records"][1]["value"])
    assert net_certs.check(https)["all_seen"]
    r = net_certs.verify(https, http)
    assert r["renewed"] and https["AURORA_TLS_MODE"] == "files" and net_certs.pending(https) is None
    with pytest.raises(net_certs.CertError, match="start first"):
        net_certs.verify(https, http)


def test_by_hand_the_daily_look_prepares_the_records_and_waits(https, monkeypatch):
    zone: dict[str, set] = {}
    http = httpx.Client(transport=httpx.MockTransport(Authority(zone)))
    monkeypatch.setitem(net_acme.DIRECTORY, "production", D + "/dir")
    https.values["AURORA_ACME_DNS"] = "manual"
    out = net_certs.renew(https, http=http)
    assert out["renewed"] is False and len(out["waiting"]["records"]) == 2
    again = net_certs.renew(https, http=http)                                     # the next day: the same order
    assert again["waiting"]["records"] == out["waiting"]["records"]
    net_certs.cancel(https)
    assert net_certs.pending(https) is None


def test_a_wildcard_s_request_names_only_what_the_order_has():
    """C485: «*.example.org» alone was asked with «example.org» as its common name; the authority refused the
    request (CSR does not specify same identifiers as Order)."""
    from aurora import net_acme
    _, der = net_acme.new_key_and_csr(["*.example.org"])
    csr = x509.load_der_x509_csr(der)
    cn = [a.value for a in csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)]
    sans = csr.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
    assert sans == ["*.example.org"] and set(cn) <= set(sans) and cn == ["*.example.org"]


def test_a_nas_copy_folder_is_mounted_by_aurora_mount_and_its_failures_said(https, tmp_path, monkeypatch):
    """AURORA_CERTS_COPY_DIR as smb://…: the files go to its folder under /mnt/aurora-certs, mounted by aurora-mount
    when it is not yet; a NAS asleep or a mount refused is said, never a wait."""
    import subprocess
    from aurora import sys_backup
    (tmp_path / "cert").mkdir()
    (tmp_path / "cert" / "fullchain.pem").write_bytes(b"-----BEGIN CERTIFICATE-----\nA\n-----END CERTIFICATE-----\n")
    (tmp_path / "cert" / "privkey.pem").write_bytes(b"k")
    mnt = tmp_path / "mnt"
    monkeypatch.setattr(net_certs, "CERTS_MOUNT", mnt)
    monkeypatch.setattr(net_certs, "_p12", lambda *a: b"p12")
    https.values["AURORA_CERTS_COPY_DIR"] = "smb://192.168.1.20/Media/Library/certificate/"
    monkeypatch.setattr(sys_backup, "nas_reachable", lambda url: False)
    assert "does not answer" in net_certs.copy(https)["error"]
    monkeypatch.setattr(sys_backup, "nas_reachable", lambda url: True)
    started, up = [], {"on": False}
    monkeypatch.setattr(sys_backup, "mounted", lambda m: up["on"])
    monkeypatch.setattr(subprocess, "run", lambda cmd, **k: started.append(cmd) or subprocess.CompletedProcess(cmd, 1, "", "refused"))
    assert "AURORA_CERTS_NAS_USER" in net_certs.copy(https)["error"] and started[0][-1] == "aurora-mount.service"
    up["on"] = True
    (mnt / "Library" / "certificate").mkdir(parents=True)
    out = net_certs.copy(https)
    assert out["copied"] and out["to"] == str(mnt / "Library" / "certificate") and len(started) == 1
    assert (mnt / "Library" / "certificate" / "keyStore.p12").read_bytes() == b"p12"


def test_the_copy_window_days_and_hours_and_the_tries_it_leaves():
    """Owner, 3 Nov: the copy right after the renewal by default, or inside a window (a NAS asleep at night)."""
    from datetime import datetime as T
    W = net_certs.window
    assert W("") is None and W("10-20") == (set(range(7)), 10, 20)
    assert W("sab,dom 9-12") == ({5, 6}, 9, 12) and W("lun-ven 18-23")[0] == {0, 1, 2, 3, 4}
    assert W("Sat,Sun 9-12")[0] == {5, 6} and W("ven-lun 8-9")[0] == {4, 5, 6, 0}
    for bad in ("sempre", "25-3", "10-10", "xyz 9-12"):
        with pytest.raises(ValueError):
            W(bad)
    sat, mon = T(2026, 11, 7, 10), T(2026, 11, 9, 10)
    assert net_certs.in_window(W("sab,dom 9-12"), sat) and not net_certs.in_window(W("sab,dom 9-12"), mon)
    night = W("ven 22-6")                                                 # across midnight: Friday's night
    assert net_certs.in_window(night, T(2026, 11, 6, 23)) and net_certs.in_window(night, T(2026, 11, 7, 3))
    assert not net_certs.in_window(night, T(2026, 11, 7, 23))
    assert net_certs.chances("10-12", T(2026, 1, 1, 0), T(2026, 1, 3, 0)) == 4
    assert net_certs.chances("", sat, mon) is None and net_certs.chances("boh", sat, mon) is None


def test_the_copy_waits_for_its_window_and_the_hourly_look_does_nothing_without_one(https, monkeypatch):
    from datetime import datetime as T
    done = []
    monkeypatch.setattr(net_certs, "copy", lambda cfg: done.append(1) or {"copied": True})
    https.values.update(AURORA_CERTS_COPY_DIR="/x", AURORA_CERTS_COPY_WINDOW="")
    assert net_certs.copy_when(https)["copied"] and len(done) == 1                       # no window: at once
    assert net_certs.copy_when(https, scheduled=True) == {"copied": False, "skipped": True} and len(done) == 1
    https.values["AURORA_CERTS_COPY_WINDOW"] = "sab,dom 9-12"
    assert net_certs.copy_when(https, T(2026, 11, 9, 10))["outside"] == "sab,dom 9-12" and len(done) == 1
    assert net_certs.copy_when(https, T(2026, 11, 7, 10), scheduled=True)["copied"] and len(done) == 2
    https.values["AURORA_CERTS_COPY_WINDOW"] = "sempre"
    assert "not a window" in net_certs.copy_when(https)["error"]


def test_a_certificate_for_the_copy_alone_and_the_p12_only_if_asked(https, tmp_path, monkeypatch):
    """Owner, 3 Nov: «un certificato solo per plex»: a share never holds the wildcard's key; the p12 by a tick."""
    dns = FakeDns()
    auth = Authority(dns.txt)
    monkeypatch.setattr(net_dnsapi, "provider", lambda cfg, client=None: dns)
    monkeypatch.setitem(net_acme.DIRECTORY, "production", D + "/dir")
    client = httpx.Client(transport=httpx.MockTransport(auth))
    seen = lambda n, v: True
    https.values.update(AURORA_ACME_DOMAINS="*.example.org", AURORA_DOMAIN="www.example.org")
    net_certs.renew(https, http=client, wait_seen=seen)
    nas = tmp_path / "share"
    nas.mkdir()
    https.values.update(AURORA_CERTS_COPY_DIR=str(nas), AURORA_CERTS_P12_PASSWORD="plex", AURORA_CERTS_COPY_NAMES="media.example.org",
                        AURORA_CERTS_P12=True)
    assert net_certs.own_due(https) == "none yet"
    out = net_certs.copy(https, http=client, wait_seen=seen)
    assert out["copied"] and net_certs.own_due(https) is None
    copied = net_https.describe((nas / "fullchain.pem").read_bytes())
    assert copied["names"] == ["media.example.org"]                                 # not the wildcard
    assert (nas / "privkey.pem").read_bytes() != (tmp_path / "cert" / "privkey.pem").read_bytes()
    _, cert, _ = pkcs12.load_key_and_certificates((nas / "keyStore.p12").read_bytes(), b"plex")
    assert cert.subject.rfc4514_string() == "CN=media.example.org"
    assert net_certs.copy(https, http=client, wait_seen=seen)["copied"] is False    # the same: not written again
    assert net_certs.status(https)["copy"]["own"]["names"] == ["media.example.org"]
    (nas / "keyStore.p12").unlink()
    https.values["AURORA_CERTS_P12"] = False
    assert net_certs.copy(https, http=client, wait_seen=seen)["copied"] is False and not (nas / "keyStore.p12").exists()
    https.values.update(AURORA_CERTS_COPY_NAMES="", AURORA_CERTS_P12=True)
    assert net_https.describe((nas / "fullchain.pem").read_bytes())["names"] == ["media.example.org"]
    net_certs.copy(https)
    assert net_https.describe((nas / "fullchain.pem").read_bytes())["names"] == ["*.example.org"]   # none asked: her own


def test_the_copy_s_own_certificate_refused_is_said_and_her_own_never_takes_its_place(https, tmp_path, monkeypatch):
    def broken(cfg, client=None):
        raise net_dnsapi.DnsError("no token")
    monkeypatch.setattr(net_dnsapi, "provider", broken)
    nas = tmp_path / "share2"
    nas.mkdir()
    https.values.update(AURORA_CERTS_COPY_DIR=str(nas), AURORA_CERTS_COPY_NAMES="media.example.org", AURORA_CERTS_P12=True)
    monkeypatch.setattr(net_acme, "account_key", lambda d: None)
    monkeypatch.setattr(net_acme.Client, "account", lambda self, e: None)
    monkeypatch.setattr(net_acme.Client, "__init__", lambda self, *a: None)
    out = net_certs.copy(https)
    assert "no token" in out["error"] and list(nas.iterdir()) == []
