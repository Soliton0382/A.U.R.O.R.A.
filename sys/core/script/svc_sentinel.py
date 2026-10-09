# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""aurora-sentinel: receives the firewall's syslog, keeps it, and reports incidents to aurora-api.

UDP on AURORA_SENTINEL_BIND; datagrams from addresses outside AURORA_SENTINEL_ALLOW are dropped
(counted in the log). Every accepted line goes to <AURORA_LOG_DIR>/firewall/firewall.log (rotated
like every log); the detector (sec_sentinel) turns patterns into incidents, posted to
POST /v1/aurora/sentinel/incident, which stores and investigates them. Defensive only.
"""
from __future__ import annotations

import signal
import socket
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx  # noqa: E402

from aurora import sys_config, sys_health, sys_log  # noqa: E402
from aurora.sec_sentinel import Detector, Recon, household, is_ips, is_private, parse, src_of  # noqa: E402

cfg = sys_config.get()
log = sys_log.get_logger("sentinel")
fw = sys_log.get_logger("firewall")
BASE = f"http://{cfg['AURORA_API_HOST']}:{cfg['AURORA_API_PORT']}"
_stop = False


def honeypot(api: httpx.Client) -> None:
    """Decoy ports (owner, 2026-10-06): nothing real listens there, so whoever opens one is looking for a way in —
    told at once as a high incident; aurora-api may block them on this machine (sec_hostfw). Nothing is read or sent."""
    ports = [int(p) for p in str(cfg["AURORA_HONEYPOT_PORTS"] or "").split(",") if p.strip().isdigit()]

    def watch(port: int) -> None:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("0.0.0.0", port))
            s.listen(16)
        except OSError as e:
            log.warning("decoy port %d not opened: %s", port, e)
            return
        log.info("decoy port %d open", port)
        while not _stop:
            s.settimeout(1.0)
            try:
                conn, (ip, _p) = s.accept()
            except (socket.timeout, OSError):
                continue
            conn.close()
            now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            incident = {"kind": "honeypot", "source": ip, "count": 1, "internal": is_private(ip), "first": now, "last": now,
                        "samples": [f"connection to decoy port {port}"],
                        "detail": {"title": f"Esca toccata: porta {port}", "why": "Su questa porta non c'è nessun servizio: "
                                   "chi la apre sta cercando un modo per entrare.", "action": "Chi è questo dispositivo? "
                                   "Se non lo riconosci, isolalo.", "port": port}}
            try:
                api.post(f"{BASE}/v1/aurora/sentinel/incident", json=incident).raise_for_status()
            except httpx.HTTPError as e:
                log.warning("decoy incident not delivered: %s", e)
    for p in ports:
        threading.Thread(target=watch, args=(p,), name=f"decoy-{p}", daemon=True).start()


def main() -> int:
    def stop(*_):
        global _stop
        _stop = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    from aurora import sys_ethics
    sys_ethics.require_intact(log)
    host, _, port = str(cfg["AURORA_SENTINEL_BIND"]).rpartition(":")
    allow = set(cfg["AURORA_SENTINEL_ALLOW"])
    sock = socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, int(port)))
    sock.settimeout(1.0)
    det = Detector(cfg["AURORA_SENTINEL_WINDOW_MIN"] * 60, cfg["AURORA_SENTINEL_DENY_THRESHOLD"],
                   cfg["AURORA_SENTINEL_SCAN_PORTS"])
    api = httpx.Client(headers={"Authorization": f"Bearer {cfg['AURORA_API_KEY']}"}, timeout=30)
    from aurora import sec_rules                       # the owner's own checks (Security page), read every minute
    rules = sec_rules.RuleSet(sec_rules.load(cfg))
    honeypot(api)
    from aurora import sec_baseline                    # what each device of the house normally does
    base = sec_baseline.Baseline(cfg)
    log.info("aurora-sentinel started: syslog on %s:%s, allowed %s", host, port, ", ".join(sorted(allow)))
    recon = Recon()                                    # chatter, then a threat going out: one high incident
    received = dropped = 0
    beat = 0.0
    while not _stop:
        if time.time() - beat > 60:
            sys_health.heartbeat(cfg, "sentinel")
            beat = time.time()
            fresh = sec_rules.load(cfg)
            if [r for r in fresh if r["on"]] != rules.rules:
                rules = sec_rules.RuleSet(fresh)
                log.info("checks of the owner: %d on", len(rules.rules))
            if dropped:
                log.warning("dropped %d datagrams from addresses not allowed", dropped)
                dropped = 0
        try:
            data, (addr, *_rest) = sock.recvfrom(65535)
        except socket.timeout:
            continue
        if addr not in allow:
            dropped += 1
            continue
        received += 1
        line = data.decode("utf-8", errors="replace").strip()
        fw.info("%s %s", addr, line)
        f = parse(line)
        quiet = household(f)                           # the house's chatter: logged and learned, never an incident
        if quiet:
            recon.chatter(src_of(f), time.time(), str(f.get("dst_port", "")))
        found = [] if quiet else [i.as_dict() for i in det.feed(f)]
        if is_ips(f):
            linked = recon.out(f, time.time())
            if linked:
                found.append(linked)
        try:
            found += base.feed(f)
        except Exception as e:  # noqa: BLE001 — the baseline never stops the sentinel
            log.warning("baseline: %s", e)
        # a threat line (IPS/ATP) is the detector's: the owner's checks would make a second incident of it (M161)
        for r, who, n, samples in ([] if quiet or is_ips(f) else rules.feed(f, src_of(f))):
            now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            found.append({"kind": f"rule:{r['id']}", "source": who, "count": n, "internal": who != "*" and is_private(who),
                          "first": now, "last": now, "samples": samples,
                          "detail": {"title": r["title"], "action": r["action"], "why": r["why"]}})
        for incident in found:
            try:
                api.post(f"{BASE}/v1/aurora/sentinel/incident", json=incident).raise_for_status()
            except httpx.HTTPError as e:
                log.warning("incident %s from %s not delivered: %s", incident["kind"], incident["source"], e)
    log.info("aurora-sentinel stopped after %d lines", received)
    return 0


if __name__ == "__main__":
    sys.exit(main())
