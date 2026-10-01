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
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx  # noqa: E402

from aurora import sys_config, sys_health, sys_log  # noqa: E402
from aurora.sec_sentinel import Detector, parse  # noqa: E402

cfg = sys_config.get()
log = sys_log.get_logger("sentinel")
fw = sys_log.get_logger("firewall")
BASE = f"http://{cfg['AURORA_API_HOST']}:{cfg['AURORA_API_PORT']}"
_stop = False


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
    log.info("aurora-sentinel started: syslog on %s:%s, allowed %s", host, port, ", ".join(sorted(allow)))
    received = dropped = 0
    beat = 0.0
    while not _stop:
        if time.time() - beat > 60:
            sys_health.heartbeat(cfg, "sentinel")
            beat = time.time()
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
        for incident in det.feed(parse(line)):
            try:
                api.post(f"{BASE}/v1/aurora/sentinel/incident", json=incident.as_dict()).raise_for_status()
            except httpx.HTTPError as e:
                log.warning("incident %s from %s not delivered: %s", incident.kind, incident.source, e)
    log.info("aurora-sentinel stopped after %d lines", received)
    return 0


if __name__ == "__main__":
    sys.exit(main())
