# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""aurora-harvester: brings new arXiv papers into the vault, round after round.

Each round (every AURORA_HARVEST_INTERVAL_H hours), for every category in
AURORA_HARVEST_CATEGORIES: the newest submissions, the first AURORA_HARVEST_PER_CATEGORY
not harvested before are downloaded and sent to aurora-api (POST /v1/aurora/import),
in the domain of their primary category (config/arxiv_domains.json). arXiv is asked at
most once every AURORA_ARXIV_DELAY_S seconds.

The harvester waits while a migration is running (a state file in
<AURORA_STATUS_DIR>/migrate/ updated in the last 15 minutes): the encoder is busy.
Harvested ids are kept in <AURORA_STATUS_DIR>/harvest/seen.json; the vault would
recognise a duplicate anyway (same text, same sid).

The owner steers it from the WebUI (kno_harvest): "harvest now" runs a round at once, also when
AURORA_HARVEST_ENABLED is off; a batch of arXiv ids or links is downloaded paper by paper, each in
the domain of its category. The state is written to <AURORA_STATUS_DIR>/harvest/status.json.
"""
from __future__ import annotations

import base64
import json
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx  # noqa: E402

from aurora import kno_harvest, sys_config, sys_health, sys_log  # noqa: E402
from aurora.kno_acquire import MAP_FILE, domain_of, parse_atom  # noqa: E402

cfg = sys_config.get()
log = sys_log.get_logger("harvester")
BASE = f"http://{cfg['AURORA_API_HOST']}:{cfg['AURORA_API_PORT']}"
STATE = cfg.path("AURORA_STATUS_DIR") / "harvest"
MIGRATE = cfg.path("AURORA_STATUS_DIR") / "migrate"
_stop = False


def migration_running() -> bool:
    return any(time.time() - p.stat().st_mtime < 900 for p in MIGRATE.glob("*.json")) if MIGRATE.is_dir() else False


class Harvester:
    def __init__(self):
        self.api = httpx.Client(headers={"Authorization": f"Bearer {cfg['AURORA_API_KEY']}"}, timeout=1800)
        self.web = httpx.Client(timeout=120, follow_redirects=True,
                                headers={"User-Agent": "Aurora knowledge harvester (personal, local)"})
        self.table = json.loads(MAP_FILE.read_text(encoding="utf-8"))["map"]
        STATE.mkdir(parents=True, exist_ok=True)
        self.seen_file = STATE / "seen.json"
        self.seen: set[str] = set(json.loads(self.seen_file.read_text())) if self.seen_file.exists() else set()
        self._last = 0.0

    def tell(self, event: str, payload: dict) -> None:
        """Report to aurora-api's activity feed (shown in the WebUI); never blocks harvesting."""
        try:
            self.api.post(f"{BASE}/v1/aurora/activity", json={"source": "harvester", "event": event, "payload": payload},
                          timeout=10)
        except httpx.HTTPError as e:
            log.warning("activity report failed: %s", e)

    def _save(self) -> None:
        tmp = self.seen_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(sorted(self.seen)))
        tmp.replace(self.seen_file)

    def _get(self, url: str, **params) -> httpx.Response:
        wait = self._last + cfg["AURORA_ARXIV_DELAY_S"] - time.time()
        if wait > 0:
            time.sleep(wait)
        try:
            return self.web.get(url, params=params or None).raise_for_status()
        finally:
            self._last = time.time()

    def category(self, cat: str) -> dict:
        want = cfg["AURORA_HARVEST_PER_CATEGORY"]
        xml = self._get(cfg["AURORA_ARXIV_API"], search_query=f"cat:{cat}", sortBy="submittedDate",
                        sortOrder="descending", start=0, max_results=want * 3).text
        fresh = [e for e in parse_atom(xml) if e.arxiv_id not in self.seen][:want]
        stats = {"category": cat, "new": 0, "chunks": 0, "failed": 0}
        for e in fresh:
            if _stop:
                break
            r = self.ingest(e, domain_of(e.category or cat, self.table))
            if r is None:
                stats["failed"] += 1
                continue
            stats["new"] += 1
            stats["chunks"] += r["written"]
        return stats

    def ingest(self, e, domain: str) -> dict | None:
        """Download one paper and import it into `domain`; None when it failed (logged)."""
        try:
            pdf = self._get(e.pdf).content
            r = self.api.post(f"{BASE}/v1/aurora/import", json={
                "name": f"{e.arxiv_id.replace('/', '_')}.pdf", "domain": domain, "title": e.title,
                "origin": f"arxiv:{e.arxiv_id}", "data": base64.b64encode(pdf).decode("ascii")}).raise_for_status().json()
        except (httpx.HTTPError, ValueError) as err:
            log.warning("%s (%s): %s", e.arxiv_id, e.title[:60], err)
            return None
        self.seen.add(e.arxiv_id)
        self._save()
        log.info("%s -> %s: %s (%d chunks, %d new)", e.arxiv_id, domain, e.title[:80], r["chunks"], r["written"])
        self.tell("harvest.paper", {"id": e.arxiv_id, "title": e.title, "domain": domain, "chunks": r["chunks"],
                                    "written": r["written"]})
        return r

    def batch(self, ids: list[str], cmd_id: str) -> None:
        """The owner's list of papers: looked up on arXiv, each imported in its category's domain."""
        t0 = time.time()
        items = [{"id": i, "state": "queued"} for i in ids]
        def show(**extra):
            kno_harvest.set_status(cfg, state="batch", batch={"cmd": cmd_id, "total": len(items), "items": items,
                                                            "started": t0, **extra})
        show()
        self.tell("harvest.batch", {"papers": len(ids)})
        found = {}
        for i in range(0, len(ids), 50):
            try:
                xml = self._get(cfg["AURORA_ARXIV_API"], id_list=",".join(ids[i:i + 50]), max_results=50).text
                found.update({e.arxiv_id: e for e in parse_atom(xml)})
            except httpx.HTTPError as err:
                log.warning("batch lookup failed: %s", err)
        for it in items:
            if _stop:
                break
            e = found.get(it["id"])
            if e is None:
                it["state"] = "not found on arXiv"
                show()
                continue
            it.update(title=e.title, domain=domain_of(e.category, self.table), state="downloading")
            show()
            r = self.ingest(e, it["domain"])
            it.update(state="done" if r else "failed", chunks=r["chunks"] if r else 0, written=r["written"] if r else 0)
            show()
        done = sum(1 for it in items if it["state"] == "done")
        log.info("batch %s: %d of %d papers in %.0f s", cmd_id, done, len(items), time.time() - t0)
        self.tell("harvest.batch_end", {"papers": done, "of": len(items), "seconds": round(time.time() - t0),
                                        "text": f"{done}/{len(items)} paper in {time.time() - t0:.0f} s"})
        show(finished=time.time())

    def round(self) -> None:
        t0 = time.time()
        totals = []
        self.tell("harvest.start", {"categories": cfg["AURORA_HARVEST_CATEGORIES"]})
        for cat in cfg["AURORA_HARVEST_CATEGORIES"]:
            if _stop:
                return
            try:
                totals.append(self.category(cat))
            except httpx.HTTPError as e:
                log.warning("category %s failed: %s", cat, e)
        new = sum(s["new"] for s in totals)
        log.info("round done in %.0f s: %d papers, %d chunks", time.time() - t0, new, sum(s["chunks"] for s in totals))
        self.tell("harvest.end", {"papers": new, "chunks": sum(s["chunks"] for s in totals),
                                  "failed": sum(s["failed"] for s in totals), "seconds": round(time.time() - t0),
                                  "text": f"{new} paper, {sum(s['chunks'] for s in totals)} passaggi"})
        sys_log.trace("harvester", "harvest.round", {"categories": totals, "seconds": round(time.time() - t0)})


def sleep(seconds: float) -> None:
    """Sleep, beating every minute so that the health check knows the harvester is alive."""
    end, beat = time.time() + seconds, 0.0
    while not _stop and time.time() < end:
        if time.time() - beat > 60:
            sys_health.heartbeat(cfg, "harvester")
            beat = time.time()
        if kno_harvest.pending(cfg):                    # the owner asked for something: wake up
            return
        time.sleep(max(0.0, min(5, end - time.time())))


def main() -> int:
    def stop(*_):
        global _stop
        _stop = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    from aurora import sys_ethics
    sys_ethics.require_intact(log)
    log.info("aurora-harvester started: %d categories, every %d h", len(cfg["AURORA_HARVEST_CATEGORIES"]),
             cfg["AURORA_HARVEST_INTERVAL_H"])
    h = Harvester()
    end = time.time() + 300                             # units start together: wait for aurora-api
    while not _stop and time.time() < end:
        try:
            sys_health.heartbeat(cfg, "harvester")
            if h.api.get(f"{BASE}/health", timeout=3).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(2)
    said_off = False
    next_round = time.time()
    while not _stop:
        if migration_running():
            log.info("a migration is running: waiting")
            h.tell("harvest.waiting", {"reason": "migration running"})
            kno_harvest.set_status(cfg, state="waiting", reason="migration running")
            sleep(900)
            continue
        for c in kno_harvest.take(cfg):                 # the owner's commands come first
            log.info("command from the owner: %s", c["cmd"])
            if c["cmd"] == "now":
                kno_harvest.set_status(cfg, state="harvesting", started=time.time())
                h.round()
                kno_harvest.set_status(cfg, last_round=time.time())
            elif c["cmd"] == "batch":
                h.batch(c.get("ids", []), c["id"])
        if not cfg["AURORA_HARVEST_ENABLED"]:
            if not said_off:
                log.info("harvesting is off (AURORA_HARVEST_ENABLED=0): idle, alive for the health check")
                said_off = True
            kno_harvest.set_status(cfg, state="off", enabled=False)
            sleep(600)
            continue
        if time.time() >= next_round:
            kno_harvest.set_status(cfg, state="harvesting", enabled=True, started=time.time())
            h.round()
            next_round = time.time() + cfg["AURORA_HARVEST_INTERVAL_H"] * 3600
            kno_harvest.set_status(cfg, last_round=time.time())
        kno_harvest.set_status(cfg, state="idle", enabled=True, next_round=next_round)
        sleep(next_round - time.time())
    log.info("aurora-harvester stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
