# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""What each device of the house normally does, and what it never did before (owner, 2026-10-06).

aurora-sentinel feeds every firewall line here. For AURORA_BASELINE_DAYS from the first line of a device (by its MAC,
else its address) Aurora only learns: the countries it talks to, the ports, the applications, the hours, the data it
sends a day. After that, a device that does something it never did is said once (an incident "behaviour:…"):
  new_country   it talks to a country never seen for it (an unknown country first: a possible leak or a compromise)
  new_port      it uses an unusual port never seen for it (not web, DNS, time, mail…)
  upload        it sent in a day more than 10 times its usual (at least 500 MB): a possible exfiltration
  new_device    a MAC never seen on the network, once the network itself has been watched for those days
Never a block: these are things to look at. The device's name comes from the network map, its maker from the MAC
(the IEEE list, downloaded with the threat lists). State in <STATUS>/security/baseline.json.
"""
from __future__ import annotations

import csv
import io
import json
import statistics
import threading
import time

from . import sys_config

COMMON_PORTS = {"53", "80", "123", "443", "853", "993", "995", "465", "587", "5223", "5228", "3478", "8080", "8443", "1900", "5353"}
NOT_A_COUNTRY = {"", "R1", "R2", "Reserved", "N/A", "-"}
UPLOAD_MIN = 500 * 2**20
_lock = threading.Lock()


# C584 (measured on the last 1,000 incidents, 12 Nov: 537 «behaviour», one device 200 «new port» in an hour, every
# other device at most 23): each device tells at most PER_DEVICE in an hour one by one, the rest in one «burst»
# incident of that hour with their count and values (still learnt, never told again); PER_HOUR in all; at most
# MAX_DEVICES followed (37 here), a forged flood of addresses no longer grows the file without end
PER_DEVICE, PER_HOUR, MAX_DEVICES = 5, 30, 1024


class Baseline:
    def __init__(self, cfg: sys_config.Config, days: float | None = None):
        self.cfg = cfg
        self.days = float(days if days is not None else cfg["AURORA_BASELINE_DAYS"])
        self.file = cfg.path("AURORA_STATUS_DIR") / "security" / "baseline.json"
        try:
            self.state = json.loads(self.file.read_text())
        except (OSError, ValueError):
            self.state = {"since": time.time(), "devices": {}, "told": []}
        self.told = set(self.state.get("told", []))
        self.saved = time.time()
        self.paced: dict[str, list[float]] = {}                 # C584: per device, when each was told
        self.all: list[float] = []
        self.bursts: dict[tuple[str, int], dict] = {}

    def save(self, force: bool = False) -> None:
        if not force and time.time() - self.saved < 60:
            return
        self.state["told"] = sorted(self.told)[-5000:]
        self.file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.file.with_suffix(".tmp")
        with _lock:
            tmp.write_text(json.dumps(self.state))
            tmp.replace(self.file)
        self.saved = time.time()

    def _learning(self, since: float, now: float) -> bool:
        return now - since < self.days * 86400

    def feed(self, f: dict, now: float | None = None) -> list[dict]:
        """One parsed firewall line → incidents (usually none)."""
        now = now or time.time()
        if f.get("log_type") != "Firewall" or f.get("src_zone") not in ("LAN", "DMZ", "WiFi", "VPN"):
            return []
        key = (f.get("src_mac") or f.get("src_ip") or "").upper()
        if not key:
            return []
        devs = self.state["devices"]
        out = []
        d = devs.get(key)
        if d is None and len(devs) >= MAX_DEVICES:
            return []                                           # C584: no device beyond the ceiling is followed
        if d is None:
            d = devs[key] = {"first": now, "ip": f.get("src_ip"), "countries": [], "ports": [], "apps": [], "hours": [0] * 24,
                             "days": {}}
            if not self._learning(self.state["since"], now) and f.get("src_mac"):
                out.append(self._say(key, "new_device", key, f, "Dispositivo mai visto nella rete",
                                     "Un indirizzo MAC mai visto ha cominciato a usare la rete.", "Verifica che sia tuo; se non lo è, isolalo."))
        d["ip"] = f.get("src_ip") or d["ip"]
        learning = self._learning(d["first"], now)
        day = time.strftime("%Y%m%d", time.localtime(now))
        d["days"][day] = d["days"].get(day, 0) + int(f.get("bytes_sent") or 0)
        if len(d["days"]) > 30:
            for k in sorted(d["days"])[:-30]:
                d["days"].pop(k)
        d["hours"][time.localtime(now).tm_hour] += 1
        country, port, app = f.get("dst_country", ""), str(f.get("dst_port") or ""), f.get("app_name", "")
        if country not in NOT_A_COUNTRY and country not in d["countries"]:
            if not learning:
                out.append(self._say(key, "new_country", country, f, f"Nuovo paese: {country}",
                                     f"Non aveva mai parlato con {country}.", "Guarda quale applicazione e se te lo aspettavi."))
            d["countries"].append(country)
        if port and port not in d["ports"] and len(d["ports"]) < 500:
            if not learning and port not in COMMON_PORTS:
                out.append(self._say(key, "new_port", port, f, f"Nuova porta: {port}",
                                     f"Non aveva mai usato la porta {port} ({app or f.get('protocol', '')}).", "Controlla il servizio."))
            d["ports"].append(port)
        if app and app not in d["apps"] and len(d["apps"]) < 300:
            d["apps"].append(app)
        past = [v for k, v in d["days"].items() if k != day]
        if not learning and len(past) >= 3:
            usual = statistics.median(past)
            if d["days"][day] > max(UPLOAD_MIN, 10 * usual):
                out.append(self._say(key, "upload", day, f, "Invio di dati insolito",
                                     f"Oggi ha inviato {d['days'][day] / 2**20:.0f} MB, di solito {usual / 2**20:.0f} MB al giorno.",
                                     "Possibile fuga di dati o un backup nuovo: verifica."))
        self.save()
        return self._paced(key, [o for o in out if o], now)

    def _paced(self, key: str, out: list[dict], now: float) -> list[dict]:
        """C584: at a person's pace — one by one up to PER_DEVICE an hour for a device and PER_HOUR in all, then one
        «burst» incident per device and hour that the later ones join (merged by kind and source, sec_incidents)."""
        told = []
        mine = [t for t in self.paced.get(key, []) if now - t < 3600]
        self.all = [t for t in self.all if now - t < 3600]
        for o in out:
            if len(mine) < PER_DEVICE and len(self.all) < PER_HOUR:
                mine.append(now)
                self.all.append(now)
                told.append(o)
                continue
            hour = int(now // 3600)
            b = self.bursts.setdefault((key, hour), {"n": 0, "values": []})
            b["n"] += 1
            b["values"] = (b["values"] + [o["detail"]["title"]])[-20:]
            stamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            told.append({"kind": "behaviour:burst", "source": o["source"], "count": 1, "internal": True,
                         "first": stamp, "last": stamp, "samples": o.get("samples", [])[:1],
                         "detail": {"title": "Molte novità da un dispositivo in un'ora",
                                    "why": f"{b['n']} cose mai fatte prima oltre le {PER_DEVICE} dette una per una "
                                           f"(le ultime: {', '.join(b['values'][-5:])}).",
                                    "action": "Guarda cosa è cambiato su quel dispositivo: un aggiornamento, un programma "
                                              "nuovo, o qualcosa che esplora la rete.",
                                    "mac": o["detail"].get("mac", ""), "values": b["values"]}})
        self.paced[key] = mine
        for k in [k for k in self.bursts if k[1] < int(now // 3600) - 1]:
            self.bursts.pop(k)
        return told

    def _say(self, key: str, kind: str, value: str, f: dict, title: str, why: str, action: str) -> dict | None:
        tag = f"{key}|{kind}|{value}"
        if tag in self.told:
            return None
        self.told.add(tag)
        now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        vendor = maker(self.cfg, f.get("src_mac", ""))
        return {"kind": f"behaviour:{kind}", "source": f.get("src_ip", key), "count": 1, "internal": True, "first": now,
                "last": now, "samples": [f.get("_raw", "")[:300]],
                "detail": {"title": title, "why": why + (f" Produttore: {vendor}." if vendor else ""), "action": action,
                           "mac": f.get("src_mac", "")}}


_oui: dict = {}


def maker(cfg: sys_config.Config, mac: str) -> str:
    """The maker of a device from its MAC (IEEE list), or "" (unknown, or a random private MAC of a phone)."""
    prefix = mac.replace(":", "").replace("-", "").upper()[:6]
    if len(prefix) < 6:
        return ""
    if not _oui:
        f = cfg.path("AURORA_STATUS_DIR") / "security" / "oui.csv"
        try:
            for row in csv.reader(io.StringIO(f.read_text(encoding="utf-8", errors="replace"))):
                if len(row) >= 3 and len(row[1]) == 6:
                    _oui[row[1].upper()] = row[2].strip()
        except OSError:
            return ""
    return _oui.get(prefix, "")


def refresh_makers(cfg: sys_config.Config) -> int:
    import httpx
    r = httpx.get("https://standards-oui.ieee.org/oui/oui.csv", timeout=120, follow_redirects=True,   # IEEE refuses
                  headers={"User-Agent": "Aurora/1.0 (+https://github.com/Soliton0382/A.U.R.O.R.A.)"})   # a bare client: 418
    r.raise_for_status()
    f = cfg.path("AURORA_STATUS_DIR") / "security" / "oui.csv"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(r.text, encoding="utf-8")
    _oui.clear()
    return r.text.count("\n")
