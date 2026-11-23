# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Social pages: statistics, ideas, drafts. Publishing always goes through the owner.

Platforms are the plugins whose manifest has a "social" section:
  {"label", "publish": {"tool", "field"}, "stats": tool, "max_chars"}
Drafts are plain posts in Aurora's voice (no links), within the platform's length, and end
with the AI disclosure (EU AI Act art. 50). Publishing is an external action: the owner's click
on "Publish" (WebUI) is the confirmation, and it is recorded in the approvals history.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path

from . import sys_config, sys_disclosure, sys_log, sys_persona, txt_lang
from .plg_host import PluginHost

SYS_DRAFT = ("\nYou write a social media post for %OWNER%'s {label} page from the content below. A classic post: "
             "no links, no hashtags spam (at most 3 relevant hashtags), engaging first line, in {lang}, at most "
             "{max_chars} characters. Plain text: no markdown (no ** bold, no # headings). Only what the content says: "
             "do not add facts, numbers, quotes, sayings or examples that are not in it. Output only the post.")
SYS_IDEAS = ("\nYou manage %OWNER%'s social pages. From the statistics and from what happened recently (conversations, "
             "new knowledge, thoughts), write in Italian: 1) a short reading of the statistics (what works, what does "
             "not, with the numbers given); 2) three concrete post ideas, each with the platform and a one-line draft. "
             "Only facts from the input. 'previous_reports' are your reports of the days before: never repeat their "
             "ideas, propose different subjects. When 'statistics_unchanged_since' is given the numbers did not move: "
             "say so in one line instead of reading them again.")
PREVIOUS = 3                 # C730: the reports of the days before given, so that their ideas are not said again
# C730: the reflections a post idea may come from — her thoughts and dreams (a morning routine publishes them, the
# owner's choice), never what retells a conversation, her logs or the house (as kno_rem.NOT_DREAMT)
NOT_DRAWN = ("session_memory", "self_review", "repair", "social_report")
# C730 (23 Nov: a neuralgia, the alarm switched on, the temperature and humidity of the house in the drafts): what the
# masker cannot see, by code. Matched on the text folded (lower case, no accents), Italian and English stems
HEALTH = re.compile(
    r"\b(nevralg|neuralg|emicran|migrain|mal di (testa|schiena|denti|gola|pancia|stomaco)|headache|febbr|fever|"
    r"raffreddor|tosse|medic[oi]\b|dottor[ei]? (mi|ha detto)|doctor|ospedal|hospital|pronto soccorso|sintom|symptom|"
    r"diagnos|terapi|therap|farmac|medicin[ae]? (da|per)|pastigl|antibiotic|antinfiammator|ibuprofen|paracetamol|"
    r"tachipirin|cortison|fisioterap|physiother|chirurg|surgery|ricover|malatti|malat[oa]\b|illness|\bsick\b|"
    r"dolor[ei]|\bpain\b|insonni|insomnia|glicemi|colesterol|pressione (arteriosa|alta|bassa)|blood pressure|"
    r"esami del sangue|analisi del sangue|blood test|allergi|visita (medica|dal)|cardiolog|dermatolog|ginecolog|"
    r"dentist|ortoped|neurolog|psicolog|psichiatr|ansia|anxiety|depressi|dieta\b|diet\b)")
HOME = re.compile(
    r"\b(allarm[ei]|alarm|antifurto|burglar|sensor[ei]|sensors?\b|telecamer|videosorveglian|security camera|cctv|"
    r"serratur|smart lock|door lock|porta (d'ingresso|di casa|blindata)|finestr[ae] apert|front door|"
    r"pres[ae] (smart|intelligent|elettric|comandat)|smart plug|termostat|thermostat|riscaldament|caldaia|heating|"
    r"climatizzator|condizionator|movimento rilevato|motion detected|casa vuota|nessuno (in|a) casa|"
    r"(binary_sensor|sensor|switch|alarm_control_panel|camera|climate|lock|cover)\.[a-z0-9_]+)"
    r"|\b(temperatur|umidit|humidit)\w*\s+(intern|indoor)"                   # «umidità interna»: next to it only
    r"|\b(temperatur|umidit|humidit|gradi|°\s?c\b)\w*\W+(?:\w+\W+){0,6}?(casa|soggiorno|salotto|camera da letto|"
    r"in camera|cucina|bagno|stanza|home\b)"
    r"|\b(casa|soggiorno|salotto|camera da letto|cucina|stanza)\w*\W+(?:\w+\W+){0,6}?"
    r"(temperatur|umidit|humidit|\d+[.,]?\d*\s?(°|gradi))")


def private_topic(text: str) -> str:
    """"health", "home" or "": the owner's health, or the house's state and security (alarm, sensors, plugs, cameras,
    the temperatures inside), named in a text — never a post's source (C730)."""
    t = "".join(c for c in unicodedata.normalize("NFKD", str(text).lower()) if not unicodedata.combining(c))
    t = t.replace("\u2019", "'")
    return "health" if HEALTH.search(t) else "home" if HOME.search(t) else ""


def platforms(host: PluginHost) -> list[dict]:
    out = []
    for p in host.plugins():
        social = p.manifest.get("social")
        if social and p.enabled:                       # a platform switched off is not offered anywhere
            out.append({"plugin": p.name, "label": social.get("label", p.name), "available": p.available,
                        "missing": p.missing, "max_chars": social.get("max_chars", 1000),
                        "publish": social.get("publish"), "photo": social.get("photo"), "video": social.get("video"),
                        "stats": social.get("stats")})
    return out


def draft(llm, content: str, targets: list[dict], cfg: sys_config.Config | None = None) -> dict[str, str]:
    cfg = cfg or sys_config.get()
    lang = txt_lang.detect(content)
    identity = sys_persona.identity(cfg)
    out = {}
    for t in targets:
        room = t["max_chars"] - len(cfg["AURORA_AI_DISCLOSURE_IT"]) - 10
        text = llm.complete(identity + SYS_DRAFT.format(label=t["label"], lang="Italian" if lang == "it" else "English",
                                                        max_chars=room), content[:6000], 700).answer.strip()
        out[t["plugin"]] = sys_disclosure.mark_text(text[:room], lang, cfg)
    return out


def public(cfg: sys_config.Config, text: str) -> bool:
    """Nothing the masker would hide: no user's name, no private value learnt or set (sec_mask), no address, phone or
    id. A memory that holds one is never drawn for a post — not even masked (N64 phase 6)."""
    from .sec_mask import Pseudonymizer
    m = Pseudonymizer(cfg)
    m.mask(text)
    # C593: when the local model did not answer, nobody looked for the names no rule can see (a person, a town, an
    # illness told in plain words): such a text is not known to be public, so it is not
    return not m.to_ph and not m.unseen


def drawn(p, cfg: sys_config.Config) -> tuple[list[str], list[str]]:
    """The recent turns and thoughts a post idea may come from: the admin's own memory only (the pages are the
    admin's; another user's chat never reaches a post), and of it only what `public` lets through."""
    from . import sys_log
    admin = sys_log.admin_name(cfg)
    if admin and getattr(p.reader, "user", None) not in (None, admin):
        return [], []
    recent = [s.text[:300] for s in p.reader.recent(8)]
    inner = [s.text[:300] for s in p.reader.recent(6, domain="reflection")
             if (getattr(s, "extra", None) or {}).get("type") not in NOT_DRAWN] \
        if p.reader.layout.shards("memory", "reflection") else []
    ok = lambda t: not private_topic(t) and public(cfg, t)           # C730: the code's filter first, then the masker
    return [t for t in recent if ok(t)], [t for t in inner if ok(t)]


def scrub(text: str) -> str:
    """The text without its lines on the owner's health or the house (C730): a report of before that held one is
    given back without it, and the new report's own drafts are kept without it."""
    return "\n".join(x for x in str(text).splitlines() if not private_topic(x)).strip()


def stats_sig(stats: dict) -> str:
    """The statistics' fingerprint: kept with a report, to tell the next one that nothing moved (C730)."""
    return hashlib.blake2b(json.dumps(stats, sort_keys=True, ensure_ascii=False).encode(), digest_size=8).hexdigest()


def previous(p, n: int = PREVIOUS) -> list:
    """The last n social reports, the newest last (C730)."""
    if not p.reader.layout.shards("memory", "reflection"):
        return []
    return [s for s in p.reader.recent(40, domain="reflection")
            if (getattr(s, "extra", None) or {}).get("type") == "social_report"][-n:]


def report(p, host: PluginHost, cfg: sys_config.Config | None = None) -> dict:
    """Statistics of every connected platform, and ideas; returned for a memory (REM)."""
    cfg = cfg or sys_config.get()
    stats = {}
    for t in platforms(host):
        if t["available"] and t["stats"]:
            r = host.call(t["plugin"], t["stats"], {})
            stats[t["label"]] = r["text"] if r["ok"] else f"not measured: {r['text'][:200]}"
    if not stats:
        return {"skipped": "no social platform connected"}
    recent, inner = drawn(p, cfg)
    before, sig = previous(p), stats_sig(stats)
    facts = {"statistics": stats, "recent_conversation": recent, "recent_thoughts": inner,
             "previous_reports": [{"at": str(s.created_at)[:10], "text": t} for s in before
                                  if (t := scrub(s.text)[:1500]) and public(cfg, t)]}
    unchanged = []                                                   # C730: the last reports with these very numbers
    for s in reversed(before):
        if (getattr(s, "extra", None) or {}).get("stats_sig") != sig:
            break
        unchanged.append(s)
    if unchanged:
        facts["statistics_unchanged_since"] = str(unchanged[-1].created_at)[:10]
    user = json.dumps(facts, ensure_ascii=False)
    text = scrub(p._for("rem").complete(sys_persona.identity(p.cfg) + SYS_IDEAS, user, 900).answer.strip())
    sys_log.get_logger("social").info("social report: %s", ", ".join(stats))
    return {"text": text, "stats": stats, "stats_sig": sig}
