# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Security incidents from the firewall: kept, investigated, closed by the owner.

An investigation is deterministic where it can be: severity by rule, public registry data about
the source network (netintel), then the reasoner writes the report and recommends defensive
actions (block, report to the provider's abuse contact). Nothing is done outside the machine
without the owner; nothing is ever looked up about persons (ethics code, level A).
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path

from . import sys_config, sys_log

_lock = threading.Lock()
SEVERITY = {"ips_alert": "high", "auth_fail": "high", "port_scan": "medium", "deny_burst": "low"}
SYS_REPORT = ("You are Aurora, defending %OWNER%'s network. Write, in Italian, a short incident report from the facts "
              "below: what happened (kind, source, how many events, when), what the public registry says about the "
              "source network, how serious it is and why, and the defensive actions you recommend (e.g. block the "
              "source on the firewall, report to the network's abuse contact with the log lines as evidence, check the "
              "internal host if the source is internal). Never suggest identifying or locating a person, and never "
              "suggest attacking back. Only the facts given; say 'non misurato' for anything missing.")


def severity(incident: dict) -> str:
    s = SEVERITY.get(incident["kind"], "low")
    if incident["kind"] == "deny_burst" and incident.get("count", 0) >= 500:
        s = "medium"
    if incident.get("internal") and s != "high":
        s = "medium" if s == "low" else "high"          # a host inside behaving badly matters more
    return s


class Incidents:
    def __init__(self, cfg: sys_config.Config | None = None):
        self.cfg = cfg or sys_config.get()
        self.file: Path = self.cfg.path("AURORA_STATUS_DIR") / "incidents.json"

    def _load(self) -> list[dict]:
        return json.loads(self.file.read_text(encoding="utf-8")) if self.file.exists() else []

    def _save(self, items: list[dict]) -> None:
        self.file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.file.with_suffix(".tmp")
        tmp.write_text(json.dumps(items[-1000:], ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.file)

    def add(self, incident: dict) -> dict:
        item = {"id": uuid.uuid4().hex[:10], "status": "open", "severity": severity(incident),
                "received": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **incident, "report": None, "intel": None}
        with _lock:
            items = self._load()
            items.append(item)
            self._save(items)
        sys_log.get_logger("sentinel").warning("incident %s: %s from %s (%s events, %s)", item["id"], item["kind"],
                                               item["source"], item.get("count"), item["severity"])
        sys_log.trace("sentinel", "incident", {k: item[k] for k in ("id", "kind", "source", "severity", "count")})
        return item

    def update(self, incident_id: str, **fields) -> dict:
        with _lock:
            items = self._load()
            item = next(i for i in items if i["id"] == incident_id)
            item.update(fields)
            self._save(items)
        return item

    def list(self, status: str | None = None, archived: bool = True) -> list[dict]:
        with _lock:
            return [i for i in reversed(self._load()) if (status is None or i["status"] == status)
                    and (archived or not i.get("archived"))]

    def archive_closed(self) -> int:
        """The closed incidents leave the Security page; they stay in the file, so the morning report and the
        statistics still count them. Returns how many were archived."""
        with _lock:
            items, n = self._load(), 0
            for i in items:
                if i["status"] != "open" and not i.get("archived"):
                    i.update(archived=True, archived_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
                    n += 1
            if n:
                self._save(items)
        return n


def investigate(pipeline, host, incident: dict, emit, cfg: sys_config.Config | None = None) -> str:
    cfg = cfg or sys_config.get()
    store = Incidents(cfg)
    intel = {}
    if not incident.get("internal"):
        for tool in ("rdap_ip", "reverse_dns", "ip_reputation"):
            r = host.call("netintel", tool, {"ip": incident["source"]})
            intel[tool] = r["text"] if r["ok"] else f"non misurato: {r['text'][:160]}"
            emit("sentinel.intel", {"tool": tool, "text": intel[tool][:600]})
    facts = {k: incident.get(k) for k in ("kind", "source", "count", "first", "last", "internal", "severity", "detail",
                                          "samples")}
    report = pipeline.llm.complete(SYS_REPORT, json.dumps({"incident": facts, "public_registry": intel},
                                                          ensure_ascii=False), 900).answer.strip()
    store.update(incident["id"], intel=intel, report=report, investigated=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    emit("sentinel.report", {"id": incident["id"], "text": report})
    return report
