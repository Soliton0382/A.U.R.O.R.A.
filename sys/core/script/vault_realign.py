#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The vault realigned: every arXiv paper once, as HTML, in its own domain (owner, 2026-10-13: «metti già in cantiere
la sostituzione di quei paper… cerchiamo di non avere più stessi paper su domini diversi… il vault deve essere solido,
se ha problemi poi è difficile valutare i livelli sopra»).

Read only first (the default, --dry-run): the knowledge's arXiv papers grouped by their id — those that came as PDF
(formulas garbled: C137) and those in more than one domain. With --apply, paper by paper, through aurora-api (the
only writer): the HTML imported as a declared replacement into the paper's domain (its primary arXiv category), and
only when it is in, every other copy removed (shards, registry, index rows, synapses: DELETE /v1/aurora/sources). A
paper arXiv has no HTML of keeps its PDF unless --drop-pdf-without-html. Resumable: <STATUS>/realign/done.json.

    python script/vault_realign.py                      # what it would do
    python script/vault_realign.py --apply [--limit 50] # do it (arXiv's pace: AURORA_ARXIV_DELAY_S between calls)
    python script/vault_realign.py --wikipedia [--fresh] [--apply]   # the Wikipedia articles, each in its domain
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from aurora import kno_arxiv, kno_dedup, kno_domain, kno_sources, mdl_router, sol_vault, sys_config  # noqa: E402
from aurora.kno_acquire import MAP_FILE, domain_of, parse_atom  # noqa: E402
from aurora.mdl_llm import LLM  # noqa: E402

UA = {"User-Agent": "Aurora/1.0 (https://github.com/Soliton0382/A.U.R.O.R.A.; vault realignment)"}


def papers(cfg) -> dict[str, list[dict]]:
    """{arxiv id: [{domain, source_id, form}]} of the knowledge, read only (the first passage of each document)."""
    layout = sol_vault.Layout.from_config(cfg, None)
    out: dict[str, list[dict]] = defaultdict(list)
    for dom in layout.domains("knowledge"):
        for shard in layout.shards("knowledge", dom):
            with sol_vault.db(shard, readonly=True) as con:
                for sid, extra in con.execute("SELECT source_id, extra FROM solitons WHERE chunk_index = 0"):
                    try:
                        e = json.loads(extra or "{}")
                    except ValueError:
                        continue
                    origin = str(e.get("origin") or "")
                    if origin.startswith("arxiv:"):
                        f = str(e.get("file") or "")
                        out[origin[6:]].append({"domain": dom, "source_id": sid,
                                                "form": "pdf" if f.endswith(".pdf") else "html"})
    return out


def articles(cfg) -> dict[str, list[dict]]:
    """{wikipedia identity: [{domain, source_id, title, text, lang}]}: v2's «wikipedia:…» and v1's «legacy:wiki_…»."""
    layout = sol_vault.Layout.from_config(cfg, None)
    out: dict[str, list[dict]] = defaultdict(list)
    for dom in layout.domains("knowledge"):
        for shard in layout.shards("knowledge", dom):
            with sol_vault.db(shard, readonly=True) as con:
                for sid, extra, title, text, lang in con.execute(
                        "SELECT source_id, extra, title, text, lang FROM solitons WHERE chunk_index = 0"):
                    try:
                        origin = str(json.loads(extra or "{}").get("origin") or sid)
                    except ValueError:
                        origin = sid
                    ident = kno_dedup.official(origin) or kno_dedup.official(sid)
                    if ident.startswith("wikipedia:"):
                        out[ident].append({"domain": dom, "source_id": sid, "title": title, "text": text[:1500], "lang": lang})
    return out


def wiki_lang_title(ident: str) -> tuple[str, str]:
    """«wikipedia:it:Anna Frank» → (it, Anna Frank); «wikipedia:Star Wars: Episode IV» → (en, Star Wars: Episode IV)."""
    rest = ident[len("wikipedia:"):]
    head, sep, tail = rest.partition(":")
    return (head, tail) if sep and re.fullmatch(r"[a-z]{2,3}", head) else ("en", rest)


def passages_of(cfg, domain: str, source_id: str) -> str:
    layout = sol_vault.Layout.from_config(cfg, None)
    parts = []
    for shard in layout.shards("knowledge", domain):
        with sol_vault.db(shard, readonly=True) as con:
            parts += con.execute("SELECT chunk_index, text FROM solitons WHERE source_id = ?", (source_id,)).fetchall()
    return "\n\n".join(r[1] for r in sorted(parts, key=lambda r: r[0]))


def _write(api, name: str, domain: str, ident: str, text: str) -> dict:
    """The article imported in `domain` as its identity's declared copy: the import's report, {} when it failed."""
    r = api.post("/v1/aurora/import", json={
        "name": re.sub(r"\W+", "_", name)[:80] + ".txt", "domain": domain, "title": name, "origin": ident,
        "licence": "CC BY-SA 4.0 (Wikipedia contributors)", "replace": True,
        "data": base64.b64encode(text.encode()).decode("ascii")})
    return r.json() if r.is_success else {"status": r.status_code}


def wikipedia(cfg, a, api, get) -> int:
    """Every Wikipedia article once, in the domain its text says (kno_domain, M195): copies merged, wrong domains
    moved — imported in the right one as a declared replacement, then the others removed. The domain chosen once is
    kept in realign/wikipedia.json; --fresh asks the chooser again for every article (the nightly check's command,
    C405: the kept choices are the ones it doubts)."""
    fresh = getattr(a, "fresh", False)
    state = cfg.path("AURORA_STATUS_DIR") / "realign" / "wikipedia.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    known = json.loads(state.read_text()) if state.exists() else {}
    groups = articles(cfg)
    reader = mdl_router.model_for("route", LLM(cfg), cfg)
    moves = merges = fine = 0
    for n, (ident, copies) in enumerate(sorted(groups.items()), 1):
        first = next((c for c in copies if not c["source_id"].startswith("legacy:")), copies[0])
        if fresh or ident not in known or "target" not in known[ident]:
            chosen = kno_domain.choose(reader, first["title"], first["text"], first["domain"])
            if known.get(ident, {}).get("target") != chosen:       # a new choice is done again, an equal one kept
                known[ident] = {"target": chosen}
            if n % 200 == 0:
                state.write_text(json.dumps(known))
        target = known[ident]["target"]
        keep = next((c for c in copies if c["domain"] == target and not c["source_id"].startswith("legacy:")), None) \
            or next((c for c in copies if c["domain"] == target), None)
        if keep and len(copies) == 1:
            fine += 1
            continue
        moves += keep is None
        merges += len(copies) > 1
        if not a.apply or known[ident].get("done"):
            continue
        if keep is None:                              # into the right domain: the article again, or its passages
            lang, title = wiki_lang_title(ident)
            try:
                name, text = kno_sources.wiki_page(get, lang or "en", title)
            except Exception:                         # noqa: BLE001 — Wikipedia not answering: the vault's own text
                name, text = first["title"], ""
            old = passages_of(cfg, first["domain"], first["source_id"])
            text = text if len(text) >= 500 else old
            # a knowledge passage is its text's hash, held once in the whole vault: the same text cannot be written
            # in the new domain while the old copies hold it (C298) — the copies go first, then the article is
            # written; if it is not, the old passages go back where they were
            removed = sum(api.delete("/v1/aurora/sources", params={"domain": c["domain"], "source_id": c["source_id"]})
                          .is_success for c in copies)
            r = _write(api, name, target, ident, text)
            if not r.get("written"):                  # a passage still found twice is another document's: not lost
                back = _write(api, first["title"], first["domain"], ident, old)
                print(f"{n:6}/{len(groups)} {ident} NOT moved ({r}): put back in {first['domain']} "
                      f"({back.get('written')} of {back.get('chunks')} passages)", flush=True)
                known[ident]["failed"] = str(r)[:200]
                continue
            known[ident]["done"] = f"{target} · {removed} removed"
            state.write_text(json.dumps(known))
            print(f"{n:6}/{len(groups)} {ident} → {target} ({r['written']} passages, {removed} copies removed)", flush=True)
            continue
        removed = 0
        for c in copies:
            if c["source_id"] == keep["source_id"] and c["domain"] == keep["domain"]:
                continue
            removed += api.delete("/v1/aurora/sources", params={"domain": c["domain"], "source_id": c["source_id"]}).is_success
        known[ident]["done"] = f"{target} · {removed} removed"
        state.write_text(json.dumps(known))
        print(f"{n:6}/{len(groups)} {ident} → {target} ({removed} copies removed)", flush=True)
    state.write_text(json.dumps(known))
    print(f"Wikipedia articles: {len(groups)} · fine {fine} · to move {moves} · with copies to merge {merges}"
          + ("" if a.apply else " (dry run)"), flush=True)
    return 0


def plan(groups: dict[str, list[dict]]) -> dict[str, list[str]]:
    todo = {"pdf_only": [], "several_domains": [], "fine": []}
    for aid, copies in groups.items():
        if all(c["form"] == "pdf" for c in copies):
            todo["pdf_only"].append(aid)
        elif len({c["domain"] for c in copies}) > 1 or len(copies) > 1:
            todo["several_domains"].append(aid)
        else:
            todo["fine"].append(aid)
    return todo


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="at most N papers this time (0 = all)")
    ap.add_argument("--wikipedia", action="store_true", help="the Wikipedia articles: one copy each, in the domain their text says")
    ap.add_argument("--fresh", action="store_true",
                    help="with --wikipedia: choose every article's domain again, not the one kept from the last run")
    ap.add_argument("--drop-pdf-without-html", action="store_true",
                    help="remove a paper that arXiv has only as PDF (otherwise kept)")
    a = ap.parse_args()
    cfg = sys_config.get()
    if a.wikipedia:
        api = httpx.Client(base_url=f"http://{cfg['AURORA_API_HOST']}:{cfg['AURORA_API_PORT']}", timeout=1800,
                           headers={"Authorization": f"Bearer {cfg['AURORA_API_KEY']}"})
        web = httpx.Client(timeout=60, follow_redirects=True, headers=UA)
        gap, last = float(cfg["AURORA_HARVEST_DELAY_S"]), [0.0]

        def wget(url, **params):
            wait = last[0] + gap - time.time()
            if wait > 0:
                time.sleep(wait)
            last[0] = time.time()
            return web.get(url, params=params or None).raise_for_status()
        return wikipedia(cfg, a, api, wget)
    groups = papers(cfg)
    todo = plan(groups)
    print(f"arXiv papers in the knowledge: {len(groups)} · as PDF only: {len(todo['pdf_only'])} · "
          f"more than one copy or domain: {len(todo['several_domains'])} · fine: {len(todo['fine'])}", flush=True)
    if not a.apply:
        for aid in todo["several_domains"][:10]:
            print("  e.g.", aid, [(c["domain"], c["form"]) for c in groups[aid]])
        print("dry run: nothing changed (--apply to do it)")
        return 0
    state_dir = cfg.path("AURORA_STATUS_DIR") / "realign"
    state_dir.mkdir(parents=True, exist_ok=True)
    done_file = state_dir / "done.json"
    done = json.loads(done_file.read_text()) if done_file.exists() else {}
    api = httpx.Client(base_url=f"http://{cfg['AURORA_API_HOST']}:{cfg['AURORA_API_PORT']}", timeout=1800,
                       headers={"Authorization": f"Bearer {cfg['AURORA_API_KEY']}"})
    web = httpx.Client(timeout=120, follow_redirects=True, headers=UA)
    gap, last = float(cfg["AURORA_ARXIV_DELAY_S"]), [0.0]

    def get(url, **params):
        wait = last[0] + gap - time.time()
        if wait > 0:
            time.sleep(wait)
        last[0] = time.time()
        return web.get(url, params=params or None).raise_for_status()

    table = json.loads(MAP_FILE.read_text(encoding="utf-8"))["map"]
    work = [x for x in todo["pdf_only"] + todo["several_domains"] if x not in done]
    work = work[:a.limit] if a.limit else work
    meta = {}
    for i in range(0, len(work), 50):                 # titles and primary categories, 50 at a time
        xml = get(cfg["AURORA_ARXIV_API"], id_list=",".join(work[i:i + 50]), max_results=50).text
        meta.update({e.arxiv_id.split("v")[0]: e for e in parse_atom(xml)})
    stats = defaultdict(int)
    for n, aid in enumerate(work, 1):
        copies, e = groups[aid], meta.get(aid)
        target = domain_of(e.category, table) if e else copies[0]["domain"]
        keep = next((c for c in copies if c["form"] == "html" and c["domain"] == target), None)
        outcome, sent, held = "", None, 0
        if keep is None:
            try:
                name, data = kno_arxiv.paper(aid, f"https://arxiv.org/pdf/{aid}", get)
                sent = {"name": name, "domain": target, "title": e.title if e else "", "origin": f"arxiv:{aid}",
                        "licence": "arXiv", "url": f"https://arxiv.org/abs/{aid}", "replace": True,
                        "data": base64.b64encode(data).decode("ascii")}
                r = api.post("/v1/aurora/import", json=sent).raise_for_status().json()
                held = int(r.get("duplicates") or 0)
                if not r.get("written"):
                    raise ValueError(f"the HTML was not written ({r.get('duplicates')} duplicates)")
                keep = {"domain": target, "source_id": r["source_id"]}
                outcome = "html in"
            except kno_arxiv.NoHTML:
                if not a.drop_pdf_without_html:
                    done[aid] = "no HTML: PDF kept"
                    stats["no_html_kept"] += 1
                    print(f"{n:5}/{len(work)} {aid} no HTML: the PDF stays", flush=True)
                    continue
                outcome = "no HTML: PDF dropped"
            except (httpx.HTTPError, ValueError) as err:
                stats["failed"] += 1
                print(f"{n:5}/{len(work)} {aid} FAILED: {err} (nothing removed)", flush=True)
                continue
        removed = 0
        for c in copies:                              # every other copy: the PDF, the other domains
            if keep and c["source_id"] == keep["source_id"] and c["domain"] == keep["domain"]:
                continue
            r = api.delete("/v1/aurora/sources", params={"domain": c["domain"], "source_id": c["source_id"]})
            removed += r.is_success
        if held and removed:                          # passages held by a removed copy are free now (C298)
            again = api.post("/v1/aurora/import", json=sent).json()
            outcome += f" · {again.get('written', 0)} of {held} passages written again"
        done[aid] = f"{outcome or 'kept ' + target} · {removed} copies removed"
        stats["realigned"] += 1
        stats["copies_removed"] += removed
        done_file.write_text(json.dumps(done))
        print(f"{n:5}/{len(work)} {aid} → {target}: {done[aid]}", flush=True)
    done_file.write_text(json.dumps(done))
    print(json.dumps(dict(stats)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
