# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""How much is left to harvest, and the room it would take (owner, 2026-10-13: «riusciamo a determinare quanto ancora
manca per avere il vault completo e una proiezione dell'eventuale spazio occupato?… le ricerche arxiv… un aggiornamento
una volta al giorno per capire fino a che numero è arrivato»).

Once a day the harvester asks each source how many documents it has — arXiv per category (opensearch:totalResults),
Europe PMC per query (hitCount, open access with full text: what the harvester takes), bioRxiv/medRxiv since 2013
(messages.total), a Wikipedia source the titles of its lists (known after its first round) — and arXiv's newest id;
the vault gives what a document of each domain weighs on disk, measured: its shards and its index divided by its
documents. Left × weight = the projection; a source that says no total stays «non misurato», never guessed.
"""
from __future__ import annotations

import datetime as dt
import re
import time

from . import kno_harvest, kno_sources, sys_config, sys_log

EVERY_S = 24 * 3600
_TOTAL = re.compile(r"<opensearch:totalResults[^>]*>(\d+)</opensearch:totalResults>")
_ID = re.compile(r"<id>https?://arxiv\.org/abs/([^<v]+)(?:v\d+)?</id>")


def arxiv_total(fetch, cfg, cat: str) -> int | None:
    xml = fetch(cfg["AURORA_ARXIV_API"], search_query=f"cat:{cat}", max_results=1).text      # 0: arXiv answers 500
    m = _TOTAL.search(xml)
    return int(m.group(1)) if m else None


ARCHIVES = ("cs", "math", "physics", "astro-ph", "cond-mat", "quant-ph", "hep-th", "stat", "eess")


def arxiv_newest(fetch, cfg) -> str | None:
    """The newest id arXiv lists today, the highest of its big archives' newest (one search over everything sorted by
    date came back with an older one: 2610.13634 while the vault held 2610.13948, 13 Oct)."""
    found = []
    for a in ARCHIVES:
        xml = fetch(cfg["AURORA_ARXIV_API"], search_query=f"cat:{a}.*", sortBy="submittedDate", sortOrder="descending",
                    max_results=1).text
        found += [x for x in _ID.findall(xml) if re.fullmatch(r"\d{4}\.\d{4,5}", x)]
    return max(found, key=lambda x: (x[:4], int(x[5:]))) if found else None


def _source_total(fetch, cfg, domain: str, n: str, spec: dict) -> int | None:
    src = spec["source"]
    if src == "arxiv":
        parts = [arxiv_total(fetch, cfg, c) for c in spec.get("categories", [])]
        return None if not parts or None in parts else sum(parts)
    if src == "europepmc":
        r = fetch(f"{kno_sources.EPMC}/search", query=f"OPEN_ACCESS:y AND HAS_FT:y AND {spec['query']}",
                  format="json", pageSize=1).json()
        return int(r.get("hitCount") or 0)
    if src in ("biorxiv", "medrxiv"):
        total = 0
        for cat in spec.get("categories") or [""]:
            r = fetch(f"https://api.biorxiv.org/details/{src}/2013-01-01/{dt.date.today().isoformat()}/0",
                      **({"category": cat.replace(" ", "_")} if cat else {})).json()
            total += int((r.get("messages") or [{}])[0].get("total") or 0)
        return total
    if src == "wikipedia":
        st = kno_sources.load_state(cfg, domain, n)
        return len(st["titles"]) if "titles" in st else None            # known after the source's first round
    return None                                        # Normattiva, GitHub, the docs: no total asked (not measured)


def _weight(cfg, domain: str) -> dict:
    """What the domain holds and weighs on disk now, measured: documents, passages, bytes of shards and index."""
    from . import sol_index, sol_vault
    layout = sol_vault.Layout.from_config(cfg, None)
    docs = chunks = db_bytes = 0
    for section in sol_vault.SECTIONS:
        if domain not in layout.domains(section):
            continue
        for shard in layout.shards(section, domain):
            db_bytes += shard.stat().st_size
            with sol_vault.db(shard, readonly=True) as con:
                row = con.execute("SELECT COUNT(*), COUNT(DISTINCT source_id) FROM solitons").fetchone()
                chunks, docs = chunks + row[0], docs + row[1]
    idx_bytes = 0
    for _section, name, files in sol_index._index_dirs(cfg):
        if name == domain:
            idx_bytes += sum(f.stat().st_size for f in files.folder.iterdir() if f.is_file())
    return {"docs": docs, "chunks": chunks, "bytes": db_bytes + idx_bytes,
            "per_doc": round((db_bytes + idx_bytes) / docs) if docs else None}


def build(fetch, cfg: sys_config.Config) -> dict:
    """The plan of every domain the owner harvests: taken, available, left, measured weight, projected room."""
    out, log = [], sys_log.get_logger("harvester")
    for domain, mode in sorted(kno_sources.modes(cfg).items()):
        if mode == "off":
            continue
        prog = kno_sources.progress(cfg, domain)
        totals, unknown = 0, []
        for n, spec in kno_sources.specs(cfg, domain):
            try:
                t = _source_total(fetch, cfg, domain, n, spec)
            except Exception as e:                    # noqa: BLE001 — one source that does not answer: said so
                log.info("plan: %s %s total not read: %s", domain, spec["source"], e)
                t = None
            if t is None:
                unknown.append(spec["source"] + (f" ({spec['lang']})" if spec.get("lang") else ""))
            else:
                totals += t
        w = _weight(cfg, domain)
        left = max(0, totals - prog["taken"]) if not unknown or totals else None
        out.append({"domain": domain, "mode": mode, "taken": prog["taken"], "available": totals or None,
                    "unknown": sorted(set(unknown)), "left": left, "done": prog["done"], **w,
                    "projected_bytes": left * w["per_doc"] if left is not None and w["per_doc"] else None})
    try:
        newest = arxiv_newest(fetch, cfg)
    except Exception:                                  # noqa: BLE001
        newest = None
    plan = {"at": time.time(), "domains": out, "arxiv_newest": newest, "arxiv_newest_taken": _newest_taken(cfg)}
    sys_log.trace("harvester", "harvest.plan", {"domains": len(out), "arxiv_newest": newest})
    return plan


def _newest_taken(cfg) -> str | None:
    """The newest arXiv id already in the vault (the harvester's seen list)."""
    import json
    f = cfg.path("AURORA_STATUS_DIR") / "harvest" / "seen.json"
    try:
        ids = [x for x in json.loads(f.read_text()) if re.fullmatch(r"\d{4}\.\d{4,5}", str(x))]
    except (OSError, ValueError):
        return None
    return max(ids, key=lambda x: (x[:4], int(x[5:]))) if ids else None


def due(cfg: sys_config.Config) -> bool:
    st = kno_harvest.status(cfg)
    if st.get("plan_at") == 0:                         # asked from the page
        kno_harvest.set_status(cfg, plan_at=None)
        return True
    return time.time() - (st.get("plan") or {}).get("at", 0) >= EVERY_S
