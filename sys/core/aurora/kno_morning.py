# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's good morning (owner, 2026-10-05): half a minute on what she did while the house slept — her dream, what
she studied and now knows, the attacks she stopped, the links and concepts that grew, the documents harvested.

Every line is a count read from what the code recorded overnight (reflections, the defence's state, the synapses'
store, the harvester's trace); a line with nothing to tell is left out. Written at AURORA_MORNING_HOUR by aurora-rem,
kept as a reflection of type "morning" (shown in the chat with 🔊), and sent as a notification.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone

from . import sys_config


def _since(hours: float = 18) -> tuple[float, str]:
    t = time.time() - hours * 3600
    return t, datetime.fromtimestamp(t, timezone.utc).isoformat()


def _harvested(cfg: sys_config.Config, since: float) -> tuple[int, int]:
    """(documents, passages) the harvester wrote since `since` (its rounds' trace)."""
    f = cfg.path("AURORA_LOG_DIR") / "trace" / "harvester.jsonl"
    docs = chunks = 0
    for line in f.read_text(encoding="utf-8", errors="replace").splitlines() if f.exists() else []:
        try:
            e = json.loads(line)
            if e.get("event") != "harvest.round" or datetime.fromisoformat(e["ts"]).timestamp() < since:
                continue
        except (ValueError, KeyError):
            continue
        for d in e.get("payload", {}).get("domains", []):
            docs += int(d.get("new", 0))
            chunks += int(d.get("chunks", 0))
    return docs, chunks


def facts(pipeline, cfg: sys_config.Config) -> dict:
    """What the night left, counted."""
    from . import kno_study, kno_synapse, sec_defence
    t, iso = _since()
    refl = pipeline.reader.recent(300, domain="reflection") if pipeline.reader.layout.shards("memory", "reflection") else []
    dream = next((s for s in reversed(refl) if s.extra.get("type") == "dream" and s.created_at >= iso), None)
    studies = kno_study.tonight(pipeline)
    blocks = [b for b in sec_defence._load(cfg) if b.get("auto") and b["at"] >= t]
    syn = kno_synapse.stats(cfg)
    docs, chunks = _harvested(cfg, t)
    return {"dream": dream.text.split("\n")[0][:200] if dream else "",
            "learned": [s.extra.get("question", "") for s in studies if s.extra.get("learned")],
            "not_yet": [s.extra.get("question", "") for s in studies if not s.extra.get("learned")],
            "blocked": len(blocks), "links_today": syn["today"], "concepts": syn["concepts"],
            "documents": docs, "passages": chunks}


def compose(f: dict, name: str, assistant: str, lang: str = "it") -> str:
    it = lang.startswith("it")
    lines = [f"☀️ {'Buongiorno' if it else 'Good morning'}{', ' + name if name else ''}! "
             + ("Ecco la mia notte." if it else "Here is my night.")]
    if f["learned"]:
        q = "; ".join(f"«{x[:90]}»" for x in f["learned"][:3])
        lines.append((f"📚 Ieri non sapevo rispondere e stanotte ho studiato: ora so rispondere su {q}."
                      if it else f"📚 Yesterday I could not answer, and tonight I studied: now I can answer {q}."))
    if f["not_yet"]:
        n = len(f["not_yet"])
        lines.append(((f"🔎 Su {n} domande ho cercato" if n > 1 else "🔎 Su una domanda ho cercato")
                      + " ma non ho ancora trovato fonti sufficienti." if it else
                      (f"🔎 For {n} questions" if n > 1 else "🔎 For one question") + " I searched but found no sufficient sources yet."))
    if f["documents"]:
        lines.append((f"🌾 Ho raccolto {f['documents']} documenti nuovi ({f['passages']} passaggi)."
                      if it else f"🌾 I harvested {f['documents']} new documents ({f['passages']} passages)."))
    if f["links_today"]:
        lines.append((f"🧠 Sono nati {f['links_today']} collegamenti fra domini diversi; i concetti sono {f['concepts']}."
                      if it else f"🧠 {f['links_today']} links grew between domains; there are {f['concepts']} concepts."))
    if f["blocked"]:
        b = f["blocked"]
        lines.append((f"🛡️ Ho fermato {b} attacchi sul firewall." if b > 1 else "🛡️ Ho fermato un attacco sul firewall.") if it
                     else (f"🛡️ I stopped {b} attacks on the firewall." if b > 1 else "🛡️ I stopped one attack on the firewall."))
    if f["dream"]:
        lines.append((f"🌙 Ho sognato: {f['dream']}" if it else f"🌙 I dreamt: {f['dream']}"))
    if len(lines) == 1:
        lines.append("Notte tranquilla: niente da raccontare." if it else "A quiet night: nothing to tell.")
    if f.get("mood"):
        lines.append(f"💗 {f['mood']}")
    lines.append(f"— {assistant}")
    return "\n\n".join(lines)


def greeted_today(pipeline) -> bool:
    today = datetime.now().astimezone().date().isoformat()
    refl = pipeline.reader.recent(100, domain="reflection") if pipeline.reader.layout.shards("memory", "reflection") else []
    return any(s.extra.get("type") == "morning" and s.extra.get("day") == today for s in refl)


def write(pipeline, cfg: sys_config.Config, emit) -> dict:
    from . import sys_persona
    from .kno_rem import Rem
    f = facts(pipeline, cfg)
    from . import kno_mood
    m = kno_mood.last(cfg)
    if m:
        f["mood"] = kno_mood.feeling(m, str(cfg["AURORA_LANG_DEFAULT"]))
    text = compose(f, str(cfg["AURORA_OWNER_NAME"] or ""), sys_persona.name(cfg), str(cfg["AURORA_LANG_DEFAULT"]))
    Rem(pipeline, cfg)._write(text, "morning", f"morning:{int(time.time())}",
                              {"day": datetime.now().astimezone().date().isoformat(), "facts": f}, emit)
    return {"text": text, **{k: (len(v) if isinstance(v, list) else v) for k, v in f.items() if k != "dream"}}
