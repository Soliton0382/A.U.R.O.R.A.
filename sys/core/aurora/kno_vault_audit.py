# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The vault watched every night, so that it never has to be realigned again (owner, 2026-10-13: «così si allinea
tutto una volta per tutte, ed è già la terza volta in questa installazione… spero non capiti nuovamente»).

Read only, once a night (aurora-rem's task «audit»): the knowledge's documents grouped by their official identity
(kno_dedup.official: an arXiv id, a Wikipedia article, a PMC id…) — more than one copy is a duplicate; the arXiv papers
still held as PDF (formulas garbled: C137, C293); a sample of Wikipedia articles read again by the domain chooser
(kno_domain): one whose domain the chooser would change is misplaced. Anything found is told to the owner (a
notification «vault.audit») with the commands that fix it; nothing is changed here."""
from __future__ import annotations

import json
import random
import time
from collections import defaultdict
from pathlib import Path

from . import kno_dedup, sol_vault, sys_config, sys_log

SAMPLE = 40            # Wikipedia articles read again a night (the local model: ~1 s each)


def _state(cfg: sys_config.Config) -> Path:
    return cfg.path("AURORA_STATUS_DIR") / "vault_audit.json"


def done_tonight(cfg: sys_config.Config) -> bool:
    try:
        return time.time() - json.loads(_state(cfg).read_text(encoding="utf-8")).get("at", 0) < 20 * 3600
    except (OSError, ValueError):
        return False


def scan(cfg: sys_config.Config) -> dict:
    """Identities with more than one copy, arXiv papers as PDF, Wikipedia articles: read from the shards."""
    layout = sol_vault.Layout.from_config(cfg, None)
    copies: dict[str, list] = defaultdict(list)
    try:                                              # arXiv has no HTML for these: the PDF is all there is
        no_html = {f"arxiv:{k}" for k, v in json.loads((cfg.path("AURORA_STATUS_DIR") / "realign" / "done.json")
                   .read_text(encoding="utf-8")).items() if str(v).startswith("no HTML")}
    except (OSError, ValueError):
        no_html = set()
    pdf, wiki = [], []
    for dom in layout.domains("knowledge"):
        for shard in layout.shards("knowledge", dom):
            with sol_vault.db(shard, readonly=True) as con:
                for sid, extra, title, text in con.execute(
                        "SELECT source_id, extra, title, text FROM solitons WHERE chunk_index = 0"):
                    try:
                        e = json.loads(extra or "{}")
                    except ValueError:
                        e = {}
                    ident = kno_dedup.official(str(e.get("origin") or sid)) or kno_dedup.official(sid)
                    if ident:
                        copies[ident.lower()].append((dom, sid))
                    if ident.startswith("arxiv:") and str(e.get("file", "")).endswith(".pdf") and ident not in no_html:
                        pdf.append(ident)
                    if ident.startswith("wikipedia:"):
                        wiki.append({"domain": dom, "title": title, "text": text[:900], "ident": ident})
    dups = {k: v for k, v in copies.items() if len(v) > 1}
    return {"duplicates": dups, "pdf": pdf, "wiki": wiki}


def audit(cfg: sys_config.Config, llm, tell=None, sample: int = SAMPLE) -> dict:
    """The night's check: what it found, told when anything is wrong."""
    from . import kno_domain
    t0 = time.time()
    s = scan(cfg)
    picked = random.Random(int(time.time() // 86400)).sample(s["wiki"], min(sample, len(s["wiki"])))
    misplaced = []
    for w in picked:
        chosen = kno_domain.choose(llm, w["title"], w["text"], w["domain"])
        if chosen != w["domain"]:
            misplaced.append({"title": w["title"], "in": w["domain"], "would_be": chosen})
    out = {"at": time.time(), "duplicates": len(s["duplicates"]), "duplicate_examples": list(s["duplicates"].items())[:5],
           "arxiv_pdf": len(s["pdf"]), "wikipedia_read": len(picked), "misplaced": len(misplaced),
           "misplaced_examples": misplaced[:5], "seconds": round(time.time() - t0)}
    _state(cfg).parent.mkdir(parents=True, exist_ok=True)
    _state(cfg).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    sys_log.trace("rem", "vault.audit", {k: v for k, v in out.items() if not k.endswith("examples")})
    if out["duplicates"] or out["arxiv_pdf"] or out["misplaced"]:
        text = (f"Controllo del vault: {out['duplicates']} documenti in più copie, {out['arxiv_pdf']} paper arXiv ancora "
                f"in PDF, {out['misplaced']} voci Wikipedia su {out['wikipedia_read']} in un dominio che non è il loro. "
                "Si sistemano con: python sys/core/script/vault_realign.py --apply (paper) e --wikipedia --apply (voci).")
        if tell:
            tell("vault.audit", {"text": text, **{k: out[k] for k in ("duplicates", "arxiv_pdf", "misplaced")}})
        out["text"] = text
    return out
