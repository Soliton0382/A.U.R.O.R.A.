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
import re
import subprocess
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
        return {"renewed": False, "why": None, "copied": copy_when(cfg)}
    if manual(cfg):                                   # by hand: the records shown, the admin adds them and verifies
        st = pending(cfg)
        return {"renewed": False, "why": why, "waiting": _public(st) if st else start(cfg, http),
                "copied": copy_when(cfg)}
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
    return {"renewed": True, "why": why, "certificate": info, "copied": copy_when(cfg)}


# ---- the guided way: start, see, verify (owner, 1 Nov: «metto il dominio, faccio partire, dà il token da aggiungere,
# lo aggiungo e poi fa la verifica del dominio… un po' più interattiva nella pagina se no si perdono pezzi») -----------
def manual(cfg: sys_config.Config) -> bool:
    return str(cfg["AURORA_ACME_DNS"]) == "manual"


def _order_file(cfg: sys_config.Config) -> Path:
    return _dir(cfg) / "order.json"


def pending(cfg: sys_config.Config) -> dict | None:
    try:
        return json.loads(_order_file(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _keep_order(cfg: sys_config.Config, st: dict | None) -> None:
    f = _order_file(cfg)
    if st is None:
        f.unlink(missing_ok=True)
        return
    f.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = f.with_suffix(f".{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as h:
        json.dump(st, h)
    os.replace(tmp, f)


def _client(cfg: sys_config.Config, staging: bool, http=None):
    from . import net_acme
    c = net_acme.Client(net_acme.account_key(_dir(cfg)), net_acme.DIRECTORY["staging" if staging else "production"], http)
    c.account(str(cfg["AURORA_ACME_EMAIL"] or ""))
    return c


def _public(st: dict, seen: dict | None = None) -> dict:
    recs = [{"name": t["name"], "value": t["value"], **({"seen": seen.get((t["name"], t["value"]), False)} if seen is not None else {})}
            for t in st["todo"]]
    return {"names": st["names"], "staging": st["staging"], "manual": st["manual"], "started": st["started"], "records": recs,
            **({"all_seen": all(r["seen"] for r in recs)} if seen is not None else {})}


def start(cfg: sys_config.Config, http=None) -> dict:
    """An order begun for the names asked: its TXT records, written by Aurora (a DNS provider) or shown to be added by
    hand. One at a time: a new start drops the one before (its records too)."""
    from . import net_acme, net_dnsapi
    cfg = net_https.fresh(cfg)
    names = wanted(cfg)
    if not names:
        raise CertError("no public name to certify: write the names (e.g. example.org, *.example.org)")
    if pending(cfg):
        cancel(cfg)
    staging, by_hand = bool(cfg["AURORA_ACME_STAGING"]), manual(cfg)
    try:
        st = _client(cfg, staging, http).begin(names)
        st.update(staging=staging, manual=by_hand, started=time.time(), refs=[])
        if not by_hand:
            dns = net_dnsapi.provider(cfg)
            for t in st["todo"]:
                st["refs"].append(dns.add_txt(t["name"], t["value"]))
    except (net_acme.AcmeError, net_dnsapi.DnsError, OSError, KeyError) as e:
        _remember(cfg, tried=time.time(), trying=False, error=str(e)[:400], steps=[])
        raise CertError(str(e)) from None
    _keep_order(cfg, st)
    _remember(cfg, tried=time.time(), trying=True, error=None,
              steps=[f"order for {', '.join(names)}{' (test service)' if staging else ''}",
                     f"{len(st['todo'])} TXT record(s) " + ("to add by hand" if by_hand else "written by Aurora")])
    _log().info("certificate: order begun for %s (%s)", ", ".join(names), "by hand" if by_hand else "DNS provider")
    return _public(st)


def check(cfg: sys_config.Config, client=None) -> dict | None:
    """The order's records as the Internet sees them now (two public resolvers), each ✅ or ⏳."""
    from . import net_dnsapi
    st = pending(cfg)
    if not st:
        return None
    seen = {}
    for name in {t["name"] for t in st["todo"]}:
        have = net_dnsapi.txt(name, client)
        for t in st["todo"]:
            if t["name"] == name:
                seen[(name, t["value"])] = t["value"] in have
    return _public(st, seen)


def verify(cfg: sys_config.Config, http=None) -> dict:
    """The authority told to look: the names validated, the certificate made, put in use and copied; the order and
    the records Aurora wrote gone either way (a refused order cannot be tried again)."""
    from . import net_acme
    cfg = net_https.fresh(cfg)
    st = pending(cfg)
    if not st:
        raise CertError("no certificate being asked: start first")
    steps = list(_state(cfg).get("steps") or [])
    try:
        chain, key = _client(cfg, st["staging"], http).complete(st)
        steps.append("names validated by the authority, certificate made")
        out = net_https.install_cert(cfg, chain, key)
        steps.append("in use: Caddy reloaded")
    except (net_acme.AcmeError, net_https.HttpsError, OSError) as e:
        _drop(cfg, st)
        _remember(cfg, trying=False, error=str(e)[:400], steps=steps + [f"refused: {str(e)[:200]}"])
        raise CertError(str(e)) from None
    _drop(cfg, st)
    info = out["certificate"]
    _remember(cfg, trying=False, error=None, issued=time.time(), staging=st["staging"], names=st["names"], steps=steps,
              not_after=info["not_after"])
    _log().info("audit: certificate issued by ACME: %s, until %s%s", ", ".join(st["names"]), info["not_after"][:10],
                " (test service)" if st["staging"] else "")
    return {"renewed": True, "certificate": info, "copied": copy_when(cfg)}


def _drop(cfg: sys_config.Config, st: dict) -> None:
    if st.get("refs"):
        from . import net_dnsapi
        try:
            dns = net_dnsapi.provider(cfg)
            for ref in st["refs"]:
                dns.remove_txt(ref)
        except Exception as e:  # noqa: BLE001 — a record left behind is harmless
            _log().warning("certificate: TXT records not removed: %s", e)
    _keep_order(cfg, None)


def cancel(cfg: sys_config.Config) -> None:
    st = pending(cfg)
    if st:
        _drop(net_https.fresh(cfg), st)
        _remember(cfg, trying=False)


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


CERTS_MOUNT = Path("/mnt/aurora-certs")               # where aurora-mount puts an smb:// copy folder (sys_nas_mount)


def _sub(url: str) -> str:
    return "/".join(p for p in url[6:].strip("/").split("/")[2:] if p)


def _mount(url: str) -> None:
    """An smb:// copy folder (owner, 3 Nov: a media server's certificate folder on the NAS) mounted by aurora-mount,
    as root, with its own NAS user; a NAS asleep is said at once, never a wait on a hanging mount (C125)."""
    from . import sys_backup
    if not sys_backup.nas_reachable(url):
        raise OSError(f"the NAS ({url[6:].split('/')[0]}) does not answer: off or asleep")
    if sys_backup.mounted(CERTS_MOUNT):
        return
    r = subprocess.run(["systemctl", "start", "aurora-mount.service"], capture_output=True, text=True, timeout=200)
    if not sys_backup.mounted(CERTS_MOUNT):
        raise OSError(f"the NAS folder is not mounted on {CERTS_MOUNT}: check AURORA_CERTS_NAS_USER and its password "
                      f"({(r.stderr or r.stdout).strip()[-200:]})")


# 🗓️ When the copy may run (owner, 3 Nov: «la copia di default a seguito del rinnovo, se no scegliamo una finestra per
# fargliela eseguire» — the NAS sleeps at night): AURORA_CERTS_COPY_WINDOW empty = at once, after each renewal and at
# the daily look; else days and hours, «10-20», «sab,dom 9-12», «lun-ven 18-23», «22-6» across midnight: only then,
# looked at every hour (svc_rem), a copy missed tried again at the next.
DAYS = {"lun": 0, "mar": 1, "mer": 2, "gio": 3, "ven": 4, "sab": 5, "dom": 6,
        "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def window(raw: str) -> tuple[set[int], int, int] | None:
    """«[days] H-H» → (weekdays, first hour, hour it ends); None when empty; ValueError when not understood."""
    raw = " ".join(str(raw or "").lower().split())
    if not raw:
        return None
    m = re.fullmatch(r"(?:([a-z,\- ]+?) )?(\d{1,2})\s*-\s*(\d{1,2})", raw)
    if not m or int(m.group(2)) > 23 or not 0 <= int(m.group(3)) <= 24 or m.group(2) == m.group(3):
        raise ValueError(f"not a window: {raw!r} (e.g. 10-20, sab,dom 9-12)")
    days: set[int] = set()
    for part in (m.group(1) or "").replace(" ", "").split(",") if m.group(1) else []:
        a, _, b = part.partition("-")
        if a[:3] not in DAYS or (b and b[:3] not in DAYS):
            raise ValueError(f"not a day: {part!r}")
        i, j = DAYS[a[:3]], DAYS[(b or a)[:3]]
        days |= {(i + k) % 7 for k in range((j - i) % 7 + 1)}
    return days or set(range(7)), int(m.group(2)), int(m.group(3))


def in_window(w: tuple[set[int], int, int] | None, now: datetime) -> bool:
    if w is None:
        return True
    days, h0, h1 = w
    if h0 < h1:
        return now.weekday() in days and h0 <= now.hour < h1
    if now.hour >= h0:                                # across midnight: the evening counts for its own day
        return now.weekday() in days
    return now.hour < h1 and (now.weekday() - 1) % 7 in days


def copy_when(cfg: sys_config.Config, now: datetime | None = None, scheduled: bool = False) -> dict | None:
    """The copy if it may run now: with no window at once (`scheduled`, the hourly look: nothing, the daily look does
    it), with one only inside it; outside, said and left to the next hour inside it."""
    cfg = net_https.fresh(cfg)
    try:
        w = window(str(cfg["AURORA_CERTS_COPY_WINDOW"] or ""))
    except ValueError as e:
        return {"copied": False, "error": str(e)}
    if (w is None and scheduled) or not str(cfg["AURORA_CERTS_COPY_DIR"] or "").strip():
        return None if not scheduled else {"copied": False, "skipped": True}
    if not in_window(w, now or datetime.now()):
        return {"copied": False, "outside": str(cfg["AURORA_CERTS_COPY_WINDOW"])}
    return copy(cfg)


def chances(raw: str, start: datetime, end: datetime) -> int | None:
    """The hours inside the window between the renewal and the certificate's end: how many tries the copy has."""
    try:
        w = window(raw)
    except ValueError:
        return None
    if w is None:
        return None
    t, n = start.replace(minute=0, second=0, microsecond=0), 0
    while t < end:
        n += in_window(w, t)
        t += timedelta(hours=1)
    return n


def copy(cfg: sys_config.Config) -> dict | None:
    """The certificate in use copied to AURORA_CERTS_COPY_DIR when the copy there is not the same; None with no folder."""
    cfg = net_https.fresh(cfg)
    raw = str(cfg["AURORA_CERTS_COPY_DIR"] or "").strip()
    if not raw:
        return None
    dest = CERTS_MOUNT / _sub(raw) if raw.startswith("smb://") else (cfg.root / os.path.expanduser(raw)).resolve()
    chain_f, key_f = cfg.path("AURORA_TLS_CERT"), cfg.path("AURORA_TLS_KEY")
    try:
        if raw.startswith("smb://"):
            _mount(raw)
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
            "manual": manual(cfg), "pending": _public(pending(cfg)) if pending(cfg) else None,
            "last": {k: st.get(k) for k in ("tried", "issued", "error", "steps", "staging", "trying")},
            "copy": {"dir": str(cfg["AURORA_CERTS_COPY_DIR"] or ""), "at": st.get("copied_at"), "error": st.get("copy_error"),
                     "window": str(cfg["AURORA_CERTS_COPY_WINDOW"] or ""),
                     "chances": chances(str(cfg["AURORA_CERTS_COPY_WINDOW"] or ""), datetime.fromisoformat(nxt).astimezone()
                                        .replace(tzinfo=None), _not_after(info).astimezone().replace(tzinfo=None))
                     if nxt else None,
                     "p12_password": bool(cfg["AURORA_CERTS_P12_PASSWORD"]), "legacy": bool(cfg["AURORA_CERTS_P12_LEGACY"])}}
