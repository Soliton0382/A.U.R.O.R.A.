# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""One-time migration of the previous installation's knowledge into the vault.

Source: the previous chunk store (a torch file with `names`, `texts`, `tipi`), read
only. Chunks are already ~4,000 characters, the size of this vault's solitons, so
each chunk becomes one soliton: the "TITOLO ...:" header becomes the title, the
"CONTENUTO ...:" label is dropped, the domain comes from the store's repaired
classification (mapped onto the taxonomy), the source id from the document name.

Not migrated (the new installation starts its memory from zero, and knowledge is
only what has a source): conversations, Aurora's own reflections and dreams,
generated security analyses, synthetic reasoning items; and, by the owner's choice
(2026-09-30), the domains religion, network_security, reasoning and wiki.

Solitons go through aurora-api (POST /v1/aurora/solitons), the only writer of vault
and index, in small batches so that answers are never blocked for long. Progress
is saved after every batch in <AURORA_STATUS_DIR>/migrate/<source>.json: stopping
and starting again resumes; anything re-sent is recognized by its sid.

    python sys/core/script/kno_migrate_legacy.py --source <store.pt> --dry-run
    python sys/core/script/kno_migrate_legacy.py --source <store.pt>
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx  # noqa: E402

from aurora import sys_config, sys_log, txt_lang  # noqa: E402
from aurora.sol_schema import load_taxonomy  # noqa: E402

EXCLUDED_ORIGINS = {"chat", "dream", "security", "reason", "json:autonomic", "json:test"}
EXCLUDED_DOMAINS = {"chat", "dreams", "philosophy", "religion", "network_security", "reasoning", "wiki"}
# Every chunk gets its real subject; "other" in the old store was medRxiv (Covid), "paper" the owner's
# paper on the Riemann zeta functional.
DOMAIN_MAP = {"medical": "medicine", "story": "history", "patent": "patents", "paper": "mathematics",
              "other": "medicine"}
# The old "patent" domain mixed the owner's patents with Italian statutes: the statutes go to law_it.
LAW_DOCS = {"dlgs10febb2005": "D.lgs. 10 febbraio 2005, n. 30 — Codice della proprietà industriale",
            "l102_07_2023": "Legge n. 102/2023 — modifiche al Codice della proprietà industriale (d.lgs. 30/2005)"}
HEADER = re.compile(r"^(TITOLO [A-Z]+(?: \([^)]*\))?|SAGGIO [^\n:]*): *([^\n]*)\n+")
LABEL = re.compile(r"^CONTENUTO(?: SCIENTIFICO)?: *")


def origin_of(name: str) -> str:
    if name.startswith("json_"):
        m = re.match(r"json_(?:\d+_)?([a-z]+)", name)
        return "json:" + (m.group(1) if m else "?")
    m = re.match(r"^[a-z]+", name)
    return m.group(0) if m else "?"


def doc_of(name: str) -> str:
    return re.sub(r"_(chunk\d+|[0-9a-f]{8})(_pt)?$", "", re.sub(r"\.pt$", "", name))


def title_from_doc(doc: str) -> str:
    t = re.sub(r"^(arxiv|pmc|biorxiv|medrxiv|wiki_classico|wiki|bibbia_wiki|bibbia|patent|paper)_", "", doc)
    return re.sub(r"_txt_done$", "", t).replace("_", " ").strip()


def clean(text: str) -> tuple[str, str]:
    """(title from the header or "", body without header and label)."""
    title = ""
    m = HEADER.match(text)
    if m:
        title, text = m.group(2).strip(), text[m.end():]
    return title, LABEL.sub("", text, count=1).strip()


def plan(store: dict, taxonomy: dict) -> tuple[list[dict], collections.Counter, collections.Counter]:
    names, texts, tipi = store["names"], store["texts"], store["tipi"]
    groups: dict[str, list[int]] = collections.defaultdict(list)
    excluded = collections.Counter()
    for i, n in enumerate(names):
        o = origin_of(n)
        if o in EXCLUDED_ORIGINS or tipi[i] in EXCLUDED_DOMAINS or texts[i].startswith("[Aurora"):
            excluded[tipi[i] if tipi[i] in EXCLUDED_DOMAINS else o] += 1
            continue
        groups[doc_of(n)].append(i)
    items, domains = [], collections.Counter()
    for doc, idx in groups.items():
        idx.sort(key=lambda i: (int(m.group(1)) if (m := re.search(r"chunk(\d+)", names[i])) else 0, i))
        for k, i in enumerate(idx):
            d = DOMAIN_MAP.get(tipi[i], tipi[i])
            law = next((t for k, t in LAW_DOCS.items() if k in doc), None)
            if law:
                d = "law_it"
            if d not in taxonomy or taxonomy[d].get("memory"):
                raise ValueError(f"{names[i]}: domain {tipi[i]!r} has no place in the taxonomy; map it in DOMAIN_MAP")
            title, body = clean(texts[i])
            if not body:                                  # a header with no content (8 in the old store)
                excluded["empty_body"] += 1
                continue
            domains[d] += 1
            items.append({"i": i, "text": body, "domain": d, "source_id": "legacy:" + doc,
                          "title": (law or title or title_from_doc(doc))[:300], "chunk_index": k, "chunk_count": len(idx),
                          "extra": {"origin": origin_of(names[i]), "legacy_name": names[i]}})
    return items, domains, excluded


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", required=True, help="the previous chunk store (.pt), read only")
    ap.add_argument("--batch", type=int, default=64, help="solitons per API call (the API is busy for its duration)")
    ap.add_argument("--limit", type=int, default=0, help="stop after this many solitons (0 = all)")
    ap.add_argument("--dry-run", action="store_true", help="report what would be migrated, write nothing")
    args = ap.parse_args()
    cfg = sys_config.get()
    log = sys_log.get_logger("migrate")
    import torch                                              # only this one-time script needs torch here
    t0 = time.time()
    store = torch.load(args.source, map_location="cpu", weights_only=False, mmap=True)
    items, domains, excluded = plan(store, load_taxonomy())
    print(f"loaded {len(store['names'])} chunks in {time.time() - t0:.0f} s; to migrate {len(items)} "
          f"({len({x['source_id'] for x in items})} documents); excluded {sum(excluded.values())}: {dict(excluded)}")
    print("domains:", dict(domains.most_common()))
    if args.dry_run:
        for x in items[::max(1, len(items) // 6)][:6]:
            print(f"  [{x['domain']}] {x['title'][:70]} | {x['text'][:90]!r}")
        return 0

    state_file = cfg.path("AURORA_STATUS_DIR") / "migrate" / (Path(args.source).stem + ".json")
    state_file.parent.mkdir(parents=True, exist_ok=True)
    # The position is only valid for the same plan: other rules give another list, so start again
    # from 0 (solitons already written come back as duplicates, without being encoded again).
    plan_id = hashlib.blake2b(json.dumps([sorted(EXCLUDED_ORIGINS), sorted(EXCLUDED_DOMAINS), DOMAIN_MAP, LAW_DOCS,
                                          len(items)], sort_keys=True).encode(), digest_size=8).hexdigest()
    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    if state.get("plan") != plan_id:
        if state:
            print(f"rules changed since the last run (plan {state.get('plan')} -> {plan_id}): starting from 0")
        state = {"source": str(args.source), "source_size": Path(args.source).stat().st_size, "plan": plan_id,
                 "next": 0, "written": 0, "duplicates": 0, "rejected": 0,
                 "started": time.strftime("%Y-%m-%dT%H:%M:%S")}
    base = f"http://{cfg['AURORA_API_HOST']}:{cfg['AURORA_API_PORT']}"
    client = httpx.Client(headers={"Authorization": f"Bearer {cfg['AURORA_API_KEY']}"}, timeout=1800)
    end = len(items) if not args.limit else min(len(items), state["next"] + args.limit)
    t_run, done_run = time.time(), 0
    while state["next"] < end:
        batch = items[state["next"]:min(end, state["next"] + args.batch)]
        for x in batch:
            x["lang"] = txt_lang.detect(x["text"])
        body = [{k: v for k, v in x.items() if k != "i"} for x in batch]
        for attempt in range(10):
            try:
                r = client.post(f"{base}/v1/aurora/solitons", json={"items": body})
                if 400 <= r.status_code < 500:            # the batch itself is wrong: retrying cannot help
                    print(f"stopped at {state['next']}: the API refused the batch ({r.status_code}): {r.text[:500]}")
                    log.error("batch at %d refused: %s %s", state["next"], r.status_code, r.text[:500])
                    return 1
                r.raise_for_status()
                break
            except httpx.HTTPError as e:                  # API restarting: wait and retry the same batch
                log.warning("batch at %d failed (%s), retry %d", state["next"], e, attempt + 1)
                time.sleep(min(60, 5 * (attempt + 1)))
        else:
            print(f"giving up at {state['next']}: API unreachable")
            return 1
        rep = r.json()
        state["next"] += len(batch)
        state["written"] += rep["written"]
        state["duplicates"] += rep["duplicates"]
        state["rejected"] += len(rep["rejected"])
        state["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        tmp = state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=1))
        tmp.replace(state_file)
        done_run += len(batch)
        rate = done_run / (time.time() - t_run)
        eta_h = (end - state["next"]) / rate / 3600 if rate else 0
        print(f"{state['next']}/{len(items)}  written {state['written']}  dup {state['duplicates']}  "
              f"rejected {state['rejected']}  {rate:.1f}/s  eta {eta_h:.1f} h", flush=True)
        log.info("migrate %d/%d written %d dup %d rejected %d rate %.2f/s",
                 state["next"], len(items), state["written"], state["duplicates"], state["rejected"], rate)
    print("done" if state["next"] >= len(items) else f"stopped at {state['next']} (--limit)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
