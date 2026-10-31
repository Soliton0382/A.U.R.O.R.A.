# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔏 A domain's DNS through its provider's API, for the ACME challenge (net_acme): a TXT record written, seen from the
Internet, removed. One driver per provider (AURORA_ACME_DNS); today Cloudflare, with a token limited to the zone's DNS.

`seen` asks two public resolvers over HTTPS (DNS-over-HTTPS, JSON) — what the authority will see, not this machine's
own resolver, which may answer from the house's DNS."""
from __future__ import annotations

import time

import httpx

from . import sys_config

DOH = ("https://cloudflare-dns.com/dns-query", "https://dns.google/resolve")


class DnsError(Exception):
    pass


class Cloudflare:
    API = "https://api.cloudflare.com/client/v4"

    def __init__(self, token: str, client: httpx.Client | None = None):
        if not token:
            raise DnsError("the DNS provider's token is not set (AURORA_ACME_DNS_TOKEN)")
        self.h = client or httpx.Client(timeout=30)
        self.headers = {"Authorization": f"Bearer {token}"}
        self.zones: dict[str, str] = {}

    def _call(self, method: str, path: str, **kw) -> dict:
        r = self.h.request(method, self.API + path, headers=self.headers, **kw)
        try:
            body = r.json()
        except ValueError:
            raise DnsError(f"Cloudflare: HTTP {r.status_code}") from None
        if not body.get("success"):
            why = "; ".join(e.get("message", "") for e in body.get("errors") or []) or f"HTTP {r.status_code}"
            raise DnsError(f"Cloudflare: {why}")
        return body

    def zone(self, name: str) -> str:
        """The zone holding `name`: its longest suffix the token can see."""
        parts = name.rstrip(".").split(".")
        for i in range(len(parts) - 1):
            cand = ".".join(parts[i:])
            if cand in self.zones:
                return self.zones[cand]
            res = self._call("GET", "/zones", params={"name": cand})["result"]
            if res:
                self.zones[cand] = res[0]["id"]
                return res[0]["id"]
        raise DnsError(f"Cloudflare: no zone for {name} with this token")

    def add_txt(self, name: str, value: str) -> str:
        zid = self.zone(name)
        rec = self._call("POST", f"/zones/{zid}/dns_records",
                         json={"type": "TXT", "name": name, "content": value, "ttl": 60})["result"]
        return f"{zid}/{rec['id']}"

    def remove_txt(self, ref: str) -> None:
        zid, rid = ref.split("/", 1)
        self._call("DELETE", f"/zones/{zid}/dns_records/{rid}")


DRIVERS = {"cloudflare": Cloudflare}


def provider(cfg: sys_config.Config, client: httpx.Client | None = None):
    kind = str(cfg["AURORA_ACME_DNS"] or "cloudflare")
    if kind not in DRIVERS:
        raise DnsError(f"DNS provider not known: {kind} ({', '.join(DRIVERS)})")
    return DRIVERS[kind](str(cfg["AURORA_ACME_DNS_TOKEN"] or ""), client)


def txt(name: str, client: httpx.Client | None = None) -> set[str]:
    """The TXT values of `name` as each public resolver answers, those every one of them has."""
    h = client or httpx.Client(timeout=10)
    seen: list[set[str]] = []
    for url in DOH:
        try:
            r = h.get(url, params={"name": name, "type": "TXT"}, headers={"accept": "application/dns-json"})
            ans = r.json().get("Answer") or []
        except (httpx.HTTPError, ValueError):
            seen.append(set())
            continue
        seen.append({str(a.get("data", "")).strip('"') for a in ans if a.get("type") == 16})
    return set.intersection(*seen) if seen else set()


def wait_seen(name: str, values: set[str], timeout: float = 180, every: float = 10, client=None, sleep=time.sleep) -> bool:
    """Until every value is public (each resolver), at most `timeout` seconds."""
    end = time.monotonic() + timeout
    while True:
        if values <= txt(name, client):
            return True
        if time.monotonic() >= end:
            return False
        sleep(every)
