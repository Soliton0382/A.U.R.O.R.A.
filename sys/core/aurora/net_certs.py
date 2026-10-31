# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔏 The HTTPS certificate looked after by Aurora (owner, 1 Nov: «sostituire il mini PC… copia dei certificati su
altro device anche in formato p12 compatibile con Plex… una copia con sovrascrittura sulla cartella del NAS»; «nella
pagina https… la scadenza, quando è previsto il rinnovo automatico»). The admin's only.

- renew: when AURORA_ACME_ENABLED and the certificate in use ends within RENEW_DAYS (or does not cover the names
  asked), a new one from the ACME authority (net_acme, DNS challenge through net_dnsapi), put in use the way an
  uploaded one is (net_https.install_cert: checked, Caddy reloaded, the old files back on any failure).
- copy: every certificate in use, new or not, copied to AURORA_CERTS_COPY_DIR (the NAS's shared folder) overwriting —
  fullchain.pem, privkey.pem, cert.pem, chain.pem and keyStore.p12 with its password — when the copy there differs.
- aurora-rem asks once a day (if_due); the page shows the state, the dates and the last try (<STATUS>/https/acme/state.json).
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import net_https, sys_config, sys_log

RENEW_DAYS = 30


def _log():
    return sys_log.get_logger("api")                 # at use: importing never reads the configuration


class CertError(Exception):
    pass


def _dir(cfg: sys_config.Config) -> Path:
    return cfg.path("AURORA_STATUS_DIR") / "https" / "acme"


def _state(cfg: sys_config.Config) -> dict:
    try:
        return json.loads((_dir(cfg) / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _remember(cfg: sys_config.Config, **kw) -> None:
    d = _dir(cfg)
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    st = {**_state(cfg), **kw}
    tmp = d / f"state.{os.getpid()}.tmp"
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, d / "state.json")


def wanted(cfg: sys_config.Config) -> list[str]:
    raw = [n.strip().lower() for n in str(cfg["AURORA_ACME_DOMAINS"] or "").split(",") if n.strip()]
    names = raw or [n for n in net_https.names(cfg) if "." in n and not n.replace(".", "").isdigit() and n != "localhost"]
    return list(dict.fromkeys(names))


def in_use(cfg: sys_config.Config) -> dict | None:
    """The certificate Caddy serves from its files: names, issuer, dates; None in Caddy's own mode or with no file."""
    f = cfg.path("AURORA_TLS_CERT")
    if str(cfg["AURORA_TLS_MODE"]) != "files" or not f.exists():
        return None
    try:
        return net_https.describe(f.read_bytes())
    except Exception:  # noqa: BLE001 — a file that does not read is said as such
        return {"error": "the certificate file does not read"}


def _not_after(info: dict) -> datetime:
    return datetime.fromisoformat(info["not_after"].replace("Z", "+00:00")).astimezone(timezone.utc)


def why_due(cfg: sys_config.Config, now: datetime | None = None) -> str | None:
    """Why a new certificate is wanted now, or None."""
    now = now or datetime.now(timezone.utc)
    info = in_use(cfg)
    if not info or "error" in info:
        return "no certificate of its own in use"
    if _not_after(info) - now < timedelta(days=RENEW_DAYS):
        return f"it ends on {info['not_after'][:10]}"
    missing = [n for n in wanted(cfg) if not any(net_https._covers(p, n) for p in info["names"])]
    if missing:
        return f"it does not cover {', '.join(missing)}"
    if bool(cfg["AURORA_ACME_STAGING"]) != bool(_state(cfg).get("staging")) and _state(cfg).get("issued"):
        return "the authority's service changed (test ↔ real)"
    return None


def renew(cfg: sys_config.Config, force: bool = False, http=None, wait_seen=None) -> dict:
    """A new certificate when due (or `force`), in use and copied; → {"renewed", "why", …}. Errors are kept for the page."""
    from . import net_acme, net_dnsapi
    cfg = net_https.fresh(cfg)
    if not cfg["AURORA_ACME_ENABLED"]:
        raise CertError("the automatic certificate is off (AURORA_ACME_ENABLED)")
    why = "asked by the admin" if force else why_due(cfg)
    if not why:
        copied = copy(cfg)
        return {"renewed": False, "why": None, "copied": copied}
    names = wanted(cfg)
    if not names:
        raise CertError("no public name to certify: set AURORA_ACME_DOMAINS or the HTTPS names")
    staging = bool(cfg["AURORA_ACME_STAGING"])
    steps: list[str] = []
    _remember(cfg, tried=time.time(), trying=True)
    try:
        dns = net_dnsapi.provider(cfg)
        client = net_acme.Client(net_acme.account_key(_dir(cfg)), net_acme.DIRECTORY["staging" if staging else "production"],
                                 http)
        client.account(str(cfg["AURORA_ACME_EMAIL"] or ""))
        chain, key = client.certificate(names, dns, wait_seen or net_dnsapi.wait_seen, steps.append)
        out = net_https.install_cert(cfg, chain, key)
    except (net_acme.AcmeError, net_dnsapi.DnsError, net_https.HttpsError, OSError) as e:
        _remember(cfg, trying=False, error=str(e)[:400], steps=steps)
        _log().warning("certificate: renewal failed (%s): %s", why, e)
        raise CertError(str(e)) from None
    info = out["certificate"]
    _remember(cfg, trying=False, error=None, issued=time.time(), staging=staging, names=names, steps=steps,
              not_after=info["not_after"])
    _log().info("audit: certificate renewed by ACME (%s): %s, until %s%s", why, ", ".join(names), info["not_after"][:10],
             " (test service)" if staging else "")
    return {"renewed": True, "why": why, "certificate": info, "copied": copy(cfg)}


# ---- the copy for the other devices -----------------------------------------------------------------------------
def _p12(cert_pem: bytes, key_pem: bytes, password: str, legacy: bool) -> bytes:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.serialization import pkcs12
    certs = x509.load_pem_x509_certificates(cert_pem)
    key = serialization.load_pem_private_key(key_pem, None)
    if not password:
        enc = serialization.NoEncryption()
    elif legacy:                                          # the older programs' encryption
        enc = (serialization.PrivateFormat.PKCS12.encryption_builder().kdf_rounds(2048)
               .key_cert_algorithm(pkcs12.PBES.PBESv1SHA1And3KeyTripleDESCBC).hmac_hash(hashes.SHA1())
               .build(password.encode()))
    else:
        enc = serialization.BestAvailableEncryption(password.encode())
    return pkcs12.serialize_key_and_certificates(b"aurora", key, certs[0], certs[1:] or None, enc)


def _split(chain: bytes) -> tuple[bytes, bytes]:
    end = b"-----END CERTIFICATE-----"
    i = chain.find(end) + len(end)
    return chain[:i].strip() + b"\n", chain[i:].strip() + (b"\n" if chain[i:].strip() else b"")


def copy(cfg: sys_config.Config) -> dict | None:
    """The certificate in use copied to AURORA_CERTS_COPY_DIR when the copy there is not the same; None with no folder."""
    cfg = net_https.fresh(cfg)
    raw = str(cfg["AURORA_CERTS_COPY_DIR"] or "").strip()
    if not raw:
        return None
    dest = cfg.path("AURORA_CERTS_COPY_DIR")
    chain_f, key_f = cfg.path("AURORA_TLS_CERT"), cfg.path("AURORA_TLS_KEY")
    try:
        if not dest.is_dir():
            raise OSError(f"{dest} is not a folder here (is the NAS mounted?)")
        chain, key = chain_f.read_bytes(), key_f.read_bytes()
        try:
            same = (dest / "fullchain.pem").read_bytes() == chain and (dest / "privkey.pem").read_bytes() == key
        except OSError:
            same = False
        if same and (dest / "keyStore.p12").exists():
            out = {"copied": False, "to": str(dest), "at": _state(cfg).get("copied_at")}
        else:
            cert, rest = _split(chain)
            files = {"fullchain.pem": chain, "privkey.pem": key, "cert.pem": cert, "chain.pem": rest,
                     "keyStore.p12": _p12(chain, key, str(cfg["AURORA_CERTS_P12_PASSWORD"] or ""),
                                          bool(cfg["AURORA_CERTS_P12_LEGACY"]))}
            for name, data in files.items():                      # overwritten in place, each file whole
                tmp = dest / f".{name}.aurora-tmp"
                tmp.write_bytes(data)
                os.replace(tmp, dest / name)
            now = time.time()
            _remember(cfg, copied_at=now, copy_error=None)
            _log().info("audit: certificate copied to %s (%d files)", dest, len(files))
            out = {"copied": True, "to": str(dest), "at": now}
    except (OSError, ValueError) as e:
        _remember(cfg, copy_error=str(e)[:300])
        _log().warning("certificate: copy to %s failed: %s", dest, e)
        return {"copied": False, "to": str(dest), "error": str(e)[:300]}
    return out


def status(cfg: sys_config.Config) -> dict:
    """What the page shows: the certificate in use, when it renews, the last try, the copy."""
    cfg = net_https.fresh(cfg)
    info, st = in_use(cfg), _state(cfg)
    nxt = None
    if info and "error" not in info:
        nxt = (_not_after(info) - timedelta(days=RENEW_DAYS)).isoformat()
    return {"enabled": bool(cfg["AURORA_ACME_ENABLED"]), "names": wanted(cfg), "dns": str(cfg["AURORA_ACME_DNS"]),
            "token_set": bool(cfg["AURORA_ACME_DNS_TOKEN"]), "staging": bool(cfg["AURORA_ACME_STAGING"]),
            "certificate": info, "renew_from": nxt, "due": why_due(cfg) if cfg["AURORA_ACME_ENABLED"] else None,
            "last": {k: st.get(k) for k in ("tried", "issued", "error", "steps", "staging", "trying")},
            "copy": {"dir": str(cfg["AURORA_CERTS_COPY_DIR"] or ""), "at": st.get("copied_at"), "error": st.get("copy_error"),
                     "p12_password": bool(cfg["AURORA_CERTS_P12_PASSWORD"]), "legacy": bool(cfg["AURORA_CERTS_P12_LEGACY"])}}
