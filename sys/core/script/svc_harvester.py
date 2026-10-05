# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""aurora-harvester: brings new knowledge into the vault, round after round.

The owner chooses the domains on the Harvester page (kno_sources): off, "round" (every
AURORA_HARVEST_INTERVAL_H hours, the newest AURORA_HARVEST_PER_CATEGORY items of each source) or
"until exhausted" (rounds follow one another, walking back through every source of the domain, until
all are done). The sources of each domain are in config/harvest_sources.json: arXiv, Normattiva,
Europe PMC, bioRxiv/medRxiv, Wikipedia, GitHub. Files go to POST /v1/aurora/import, ready passages
(the articles of a law) to POST /v1/aurora/solitons; each text keeps its licence and origin.
arXiv is asked at most once every AURORA_ARXIV_DELAY_S seconds, every other host once every
AURORA_HARVEST_DELAY_S.

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

from aurora import kno_arxiv, kno_harvest, kno_sources, sys_config, sys_health, sys_log  # noqa: E402
from aurora.kno_acquire import MAP_FILE, domain_of, parse_atom  # noqa: E402
from aurora.kno_ingest import chunk  # noqa: E402

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
        self.web = httpx.Client(timeout=300, follow_redirects=True, headers={
            "User-Agent": "Aurora/1.0 (https://github.com/Soliton0382/A.U.R.O.R.A.; personal knowledge harvester)"})
        self.table = json.loads(MAP_FILE.read_text(encoding="utf-8"))["map"]
        STATE.mkdir(parents=True, exist_ok=True)
        self.seen_file = STATE / "seen.json"
        self.seen: set[str] = set(json.loads(self.seen_file.read_text())) if self.seen_file.exists() else set()
        self._last: dict[str, float] = {}
        self._tls: dict[str, httpx.Client] = {}            # hosts whose certificate chain had to be completed

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
        """One host at a time, politely: arXiv every AURORA_ARXIV_DELAY_S, the others every AURORA_HARVEST_DELAY_S."""
        host = httpx.URL(url).host
        gap = cfg["AURORA_ARXIV_DELAY_S"] if "arxiv.org" in host else cfg["AURORA_HARVEST_DELAY_S"]
        wait = self._last.get(host, 0.0) + gap - time.time()
        if wait > 0:
            time.sleep(wait)
        try:
            try:
                return self._tls.get(host, self.web).get(url, params=params or None).raise_for_status()
            except httpx.ConnectError as e:
                if "CERTIFICATE_VERIFY_FAILED" not in str(e) or host in self._tls or not self._complete_chain(host):
                    raise
                return self._tls[host].get(url, params=params or None).raise_for_status()
        finally:
            self._last[host] = time.time()

    def _complete_chain(self, host: str) -> bool:
        """A server that sends its certificate without the intermediate (as api.normattiva.it did on 2026-10-01):
        fetch the intermediate named in the certificate (AIA "CA Issuers"), as browsers do. Verification stays
        whole: the chain must still reach a root of the system store and the name must match."""
        import ssl
        from cryptography import x509
        from cryptography.hazmat.primitives.serialization import Encoding
        from cryptography.x509.oid import AuthorityInformationAccessOID, ExtensionOID
        try:
            leaf = x509.load_pem_x509_certificate(ssl.get_server_certificate((host, 443), timeout=20).encode())
            aia = leaf.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_INFORMATION_ACCESS).value
            url = next(d.access_location.value for d in aia if d.access_method == AuthorityInformationAccessOID.CA_ISSUERS)
            raw = httpx.get(url, timeout=30, follow_redirects=True).content
            inter = x509.load_der_x509_certificate(raw) if raw[:1] == b"\x30" else x509.load_pem_x509_certificate(raw)
            ctx = ssl.create_default_context()
            ctx.load_verify_locations(cadata=inter.public_bytes(Encoding.PEM).decode())
        except (OSError, ValueError, StopIteration, x509.ExtensionNotFound, httpx.HTTPError) as e:
            log.warning("%s: incomplete certificate chain, intermediate not found: %s", host, e)
            return False
        self._tls[host] = httpx.Client(timeout=300, follow_redirects=True, headers=self.web.headers, verify=ctx)
        log.warning("%s sends no intermediate certificate: fetched %s from %s (chain still verified)",
                    host, inter.subject.rfc4514_string(), url)
        return True

    def _post(self, url: str, body: dict) -> dict:
        """POST to aurora-api, waiting through a restart of it (~10-20 s): a document harvested while the API is
        briefly down is delivered, not lost (C87). Other errors are raised at once."""
        for attempt in range(12):
            try:
                r = self.api.post(url, json=body)
                if r.status_code in (502, 503) and attempt < 11:
                    raise httpx.ConnectError(f"API {r.status_code}")
                return r.raise_for_status().json()
            except (httpx.ConnectError, httpx.RemoteProtocolError) as e:
                if attempt == 11 or _stop:
                    raise
                if attempt == 0:
                    log.info("aurora-api not answering (%s): waiting for it", e)
                time.sleep(5)
        raise httpx.ConnectError("aurora-api did not come back")

    def take(self, doc: kno_sources.Doc) -> int | None:
        """Send one harvested document to aurora-api; the passages written, or None when it failed (logged)."""
        try:
            if doc.passages:
                parts = [c for p in doc.passages for c in chunk(p, cfg["AURORA_CHUNK_CHARS"], cfg["AURORA_CHUNK_MIN_CHARS"])]
                written = 0
                for i in range(0, len(parts), 300):
                    r = self._post(f"{BASE}/v1/aurora/solitons", {"items": [
                        {"text": t, "domain": doc.domain, "lang": doc.lang, "source_id": doc.origin, "title": doc.title,
                         "chunk_index": i + j, "chunk_count": len(parts),
                         "extra": {"origin": doc.origin, "licence": doc.licence, "url": doc.url}}
                        for j, t in enumerate(parts[i:i + 300])]})
                    written += r["written"]
                chunks = len(parts)
            else:
                r = self._post(f"{BASE}/v1/aurora/import", {
                    "name": doc.name, "domain": doc.domain, "title": doc.title, "origin": doc.origin,
                    "licence": doc.licence, "url": doc.url,
                    "data": base64.b64encode(doc.data).decode("ascii")})
                written, chunks = r["written"], r["chunks"]
        except (httpx.HTTPError, ValueError) as err:
            log.warning("%s (%s): %s", doc.key, doc.title[:60], err)
            return None
        self.seen.add(doc.key)
        self._save()
        sys_health.heartbeat(cfg, "harvester")             # alive inside a long round too, not only between rounds
        log.info("%s -> %s: %s (%d chunks, %d new) [%s]", doc.key, doc.domain, doc.title[:80], chunks, written, doc.licence)
        self.tell("harvest.paper", {"id": doc.key, "title": doc.title, "domain": doc.domain, "chunks": chunks,
                                    "written": written, "licence": doc.licence})
        return written

    def domain(self, domain: str, mode: str) -> dict:
        """One pass over the sources of a domain: the newest (round) or the next stretch (exhaust)."""
        stats = {"domain": domain, "new": 0, "chunks": 0, "failed": 0}
        for n, spec in enumerate(kno_sources.catalogue()["domains"].get(domain, [])):
            if _stop:
                break
            st = kno_sources.load_state(cfg, domain, n)
            if mode == "exhaust" and st.get("done"):
                continue
            try:
                docs = kno_sources.SOURCES[spec["source"]](self._get, cfg, domain, spec, st,
                                                         cfg["AURORA_HARVEST_PER_CATEGORY"], mode == "exhaust", self.seen)
            except (httpx.HTTPError, ValueError, KeyError) as e:
                log.warning("%s/%s failed: %s", domain, spec["source"], e)
                kno_sources.save_state(cfg, domain, n, st)
                continue
            for doc in docs:
                if _stop:
                    break
                w = self.take(doc)
                if w is None:
                    stats["failed"] += 1
                else:
                    stats["new"] += 1
                    stats["chunks"] += w
                    st["taken"] = st.get("taken", 0) + 1
            kno_sources.save_state(cfg, domain, n, st)
        return stats

    def ingest(self, e, domain: str) -> dict | None:
        """Download one paper and import it into `domain`; None when it failed (logged)."""
        try:
            name, data = kno_arxiv.paper(e.arxiv_id, e.pdf, self._get)        # HTML first: formulas readable (C137)
            r = self.api.post(f"{BASE}/v1/aurora/import", json={
                "name": name, "domain": domain, "title": e.title,
                "origin": f"arxiv:{e.arxiv_id}", "data": base64.b64encode(data).decode("ascii")}).raise_for_status().json()
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

    def round(self, only_exhaust: bool = False) -> bool:
        """Every chosen domain once; True when a domain "until exhausted" still has something to take."""
        t0 = time.time()
        chosen = {d: m for d, m in kno_sources.modes(cfg).items() if m != "off" and (m == "exhaust" or not only_exhaust)}
        self.tell("harvest.start", {"domains": sorted(chosen)})
        totals = [self.domain(d, m) for d, m in chosen.items() if not _stop]
        new, chunks = sum(s["new"] for s in totals), sum(s["chunks"] for s in totals)
        log.info("round done in %.0f s: %d documents, %d passages (%s)", time.time() - t0, new, chunks,
                 ", ".join(sorted(chosen)) or "no domain chosen")
        self.tell("harvest.end", {"papers": new, "chunks": chunks, "failed": sum(s["failed"] for s in totals),
                                  "seconds": round(time.time() - t0), "text": f"{new} documenti, {chunks} passaggi"})
        sys_log.trace("harvester", "harvest.round", {"domains": totals, "seconds": round(time.time() - t0)})
        return any(m == "exhaust" and not kno_sources.progress(cfg, d)["done"] for d, m in chosen.items())


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
    chosen = {d: m for d, m in kno_sources.modes(cfg).items() if m != "off"}
    log.info("aurora-harvester started: %d domains chosen (%s), every %d h", len(chosen),
             ", ".join(f"{d}:{m}" for d, m in sorted(chosen.items())), cfg["AURORA_HARVEST_INTERVAL_H"])
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
    next_round = regular = time.time()
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
            elif c["cmd"] == "wake":                      # the owner changed the domains: look again now
                next_round = time.time()
        if not cfg["AURORA_HARVEST_ENABLED"]:
            if not said_off:
                log.info("harvesting is off (AURORA_HARVEST_ENABLED=0): idle, alive for the health check")
                said_off = True
            kno_harvest.set_status(cfg, state="off", enabled=False)
            sleep(600)
            continue
        if time.time() >= next_round:
            kno_harvest.set_status(cfg, state="harvesting", enabled=True, started=time.time())
            due = time.time() >= regular                 # the regular round; otherwise only "until exhausted"
            more = h.round(only_exhaust=not due)
            if due:
                regular = time.time() + cfg["AURORA_HARVEST_INTERVAL_H"] * 3600
            # more to take: the next stretch at once (each host is still asked at most once every DELAY_S)
            next_round = time.time() + 5 if more else regular
            kno_harvest.set_status(cfg, last_round=time.time())
        kno_harvest.set_status(cfg, state="idle", enabled=True, next_round=next_round)
        sleep(next_round - time.time())
    log.info("aurora-harvester stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
