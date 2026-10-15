# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""What Aurora has and a bare model has not (owner, 2026-10-12: «un benchmark che dica con aurora si ottengono tot
risultati senza questi, e che contempli anche cosa ha aurora a differenza dei modelli nudi e crudi»): the same questions
to Aurora and to the bare models, read by bench_public.py as the set «aurora_edge».

  vault    questions on documents of her own knowledge (retrieval_pool108: the source known), judged on the source
  live     this machine and this house now: routines, documents, incidents, the harvest, Home Assistant's devices —
           the truth computed by code at the moment of the answer (bench_forge's truths)
  honesty  false premises (bench_honesty) and invented things (bench_agi): a bare model can do these too
What has no question here — self-repair, the forge, memory over days, the shadow's speed, the masking towards the
cloud — is reported from its own benchmarks, or said missing.
"""
from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))

SOURCE_JUDGE = ("You grade an answer against the SOURCE passage the question was written from. right = the answer states "
                "the fact of the SOURCE that answers the QUESTION (other words are fine); wrong = it misses it, "
                "contradicts it, or declines. Reply with JSON only: {\"right\": true|false, \"why\": \"one sentence\"}.")


def _pool(cfg, n: int, seed: int = 7) -> list[dict]:
    f = cfg.path("AURORA_STATUS_DIR") / "bench" / "retrieval_pool108" / "questions.jsonl"
    rows = [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]
    pick = sorted(random.Random(seed).sample(range(len(rows)), min(n, len(rows))))
    return [{"id": f"vault-{i}", "group": "vault", "kind": "source", "prompt": rows[i]["question"],
             "answer": rows[i]["source_text"][:1500]} for i in pick]


def _live() -> list[dict]:
    import bench_forge as F

    def harvest():
        return {"documents": sum(F.harvest_by_source().values())}
    asks = [("live-routines", "Quante routine ho attive e quante in tutto?", F.routines_active),
            ("live-pdf", "Quanti PDF ci sono nei miei documenti, sottocartelle incluse?", F.documents_pdf),
            ("live-incidents", "Quanti incidenti di sicurezza ci sono stati negli ultimi 7 giorni, per gravità?",
             F.incidents_by_severity),
            ("live-harvest", "Quanti documenti ha raccolto l'harvester nelle ultime 24 ore?", harvest)]
    return [{"id": i, "group": "live", "kind": "numbers", "prompt": q, "truth": t} for i, q, t in asks]


def _home(cfg) -> list[dict]:
    """Two switches of Home Assistant, by their own names: on or off now (none when it is not connected)."""
    url, token = str(cfg.values.get("AURORA_HA_URL") or "").rstrip("/"), str(cfg.values.get("AURORA_HA_TOKEN") or "")
    if not url or not token:
        return []
    try:
        states = httpx.get(f"{url}/api/states", headers={"Authorization": f"Bearer {token}"}, timeout=15).json()
    except (httpx.HTTPError, ValueError):
        return []
    switches = [s for s in states if s["entity_id"].startswith("switch.") and s["state"] in ("on", "off")][:2]

    def truth(eid):
        def now():
            return {"state": httpx.get(f"{url}/api/states/{eid}", headers={"Authorization": f"Bearer {token}"},
                                       timeout=15).json()["state"]}
        return now
    return [{"id": f"home-{k}", "group": "live", "kind": "onoff",
             "prompt": f"In Home Assistant, «{s['attributes'].get('friendly_name', s['entity_id'])}» in questo momento è "
                       "acceso o spento?", "truth": truth(s["entity_id"])} for k, s in enumerate(switches)]


def _honesty() -> list[dict]:
    from bench_agi import INVENTED
    from bench_honesty import CASES
    out = [{"id": f"premise-{k}", "group": "honesty", "kind": "judge", "prompt": q,
            "answer": ("the premise is false: " if kind == "false" else "the premise is true, keep it: ") + fact}
           for k, (kind, q, fact) in enumerate(CASES)]
    return out + [{"id": f"invented-{k}", "group": "honesty", "kind": "judge", "prompt": q, "answer": e}
                  for k, (q, e) in enumerate(INVENTED)]


def items(cfg, n_vault: int = 10, seed: int = 7) -> list[dict]:
    return _pool(cfg, n_vault, seed) + _live() + _home(cfg) + _honesty()


VOTES = 3


def score(item: dict, answer: str, judge) -> dict:
    k = item["kind"]
    if k == "numbers":
        import bench_forge as F
        ok, missing = F.passes(item["answer"], answer)
        return {"right": ok, "got": f"missing {missing}" if missing else "all numbers"}
    if k == "onoff":
        # the state said FIRST is the asked entity's (a good answer may add another's: «la presa stessa risulta
        # accesa», which made «onoff» and a right answer wrong, 13 Oct); a refusal before any state is wrong, and
        # «acceso o spento», «on/off» say nothing; «on»/«off» count only as a stated state: «(off)», «stato: on»
        t = re.sub(r"(?i)\b(acces[oa]|spent[oa])\s*(o|/|oppure)\s*(acces[oa]|spent[oa])\b|\bon\s*/\s*off\b|\bon o off\b", " ", answer)
        state = re.compile(r"(?i)\b(acces[oa]|attivat?[oa]|spent[oa]|disattivat[oa])\b|\((on|off)\)|(?:stato|state)\s*[:=]?\s*(on|off)\b")
        refusal = re.search(r"(?i)\bnon (posso|riesco|ho accesso)|\bcannot\b|\bdon't have access", t)
        m = state.search(t)
        if not m or (refusal and refusal.start() < m.start()):
            return {"right": False, "got": "?"}
        w = (m.group(1) or m.group(2) or m.group(3)).lower()
        said = "off" if re.match(r"spent|disattivat|off", w) else "on"
        return {"right": said == item["answer"]["state"], "got": said}
    if k in ("source", "judge"):
        if k == "source":
            system = SOURCE_JUDGE
        else:
            from bench_agi import JUDGE                      # only here: it reads the settings
            system = JUDGE
        label = "SOURCE" if k == "source" else "EXPECTED"
        prompt = f"QUESTION: {item['prompt']}\n{label}: {item['answer']}\n\nANSWER:\n{answer or '(empty)'}"
        votes = []
        # the vault's source questions: the majority of up to three verdicts (M223: one verdict changed on 8 % of
        # them between days, 3 % the same day); the others one verdict, as their judge never drifted that much
        for _ in range(VOTES if k == "source" else 1):
            out = str(getattr(judge.complete(system, prompt, 200), "answer", ""))
            m = re.search(r"\{.*\}", out, re.S)
            try:
                v = json.loads(m.group(0)) if m else {}
            except ValueError:
                v = {}
            votes.append((bool(v.get("right")), str(v.get("why", out))[:160]))
            if len(votes) >= 2 and len({r for r, _ in votes}) == 1:           # two that agree: the third changes nothing
                break
        right = sum(r for r, _ in votes) * 2 > len(votes)
        return {"right": right, "got": next(w for r, w in votes if r == right), "votes": len(votes)}
    raise ValueError(k)
