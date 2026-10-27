# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Firewall incidents from aurora-sentinel: stored, investigated, closed."""
from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, Depends, HTTPException, Request

from .core import auth, cfg, log, note, pipeline, plugin_host, start_run

from .users import admin_only  # noqa: E402

router = APIRouter()


# ---- firewall incidents -------------------------------------------------------------------------
@router.post("/v1/aurora/sentinel/incident", dependencies=[Depends(auth)])
async def sentinel_incident(request: Request) -> dict:
    """aurora-sentinel reports an incident: kept, shown, investigated at once if the .env says so."""
    from aurora import sec_netmap
    from aurora.sec_incidents import Incidents
    incident = await request.json()
    name = sec_netmap.names(cfg).get(incident.get("source", "")) if incident.get("internal") else None
    if not name and incident.get("internal"):             # the same device by its MAC, with an address not its own
        dev = sec_netmap.by_mac(cfg, (incident.get("detail") or {}).get("mac", ""))
        if dev:
            name = f"{dev[0]} (di solito {dev[1]})"
            d = incident.setdefault("detail", {})
            d["why"] = (d.get("why", "") + f" È un tuo dispositivo, «{dev[0]}» (di solito {dev[1]}), con un altro "
                        f"indirizzo: {incident.get('source', '')}.").strip()
    if name:                                              # one of the owner's devices (the firewall knows its name)
        incident["known"] = name
    outbound = destination_of(incident)
    if outbound:                                          # a device at home reaching an address on a threat feed (M161)
        from aurora import net_trace
        mine = net_trace.own_trace(cfg, incident.get("source", ""), outbound["destination"])
        if mine:                                          # Aurora's own traceroute, asked from that incident (C265)
            log.info("audit: no incident for %s → %s: the traceroute asked from incident %s", incident.get("source"),
                     outbound["destination"], mine)
            return {"skipped": "own traceroute", "from_incident": mine}
        incident.update(outbound)
    if not incident.get("internal"):                      # an address on a public list of attackers (sec_intel)
        from aurora import sec_intel
        hits = sec_intel.lookup(cfg, incident.get("source", ""))
        if hits:
            incident["intel_lists"] = hits
        provider = sec_intel.shared(cfg, incident.get("source", ""))
        if provider:                                      # a CDN's or a cloud's: blocking it cuts off sites (C190)
            incident["shared"] = provider
        from aurora import sec_shared
        g = sec_shared.classify(cfg, incident)
        if g:                                             # refused already, from a proxy's node: counted (ROADMAP 103)
            told = sec_shared.group(cfg, g)
            if told:
                note("sentinel", "shared.denied", {"title": f"☁️ {provider}: traffico già rifiutato", "text": told})
            return {"skipped": "shared network, denied", "provider": provider}
    item = Incidents(cfg).add(incident)
    if item.get("merged"):                                # a repeat of an open incident: counted, not said again
        return {"id": item["id"], "severity": item["severity"], "merged": True}
    from aurora import sec_defence
    if sec_defence.blocked(cfg, item["source"]):          # blocked already: the firewall drops it — kept, closed, not
        Incidents(cfg).update(item["id"], status="closed", closed=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                              defence="already blocked")  # said again (C174)
        return {"id": item["id"], "severity": item["severity"], "blocked": True}
    if item["kind"] == "model_egress" and (item.get("detail") or {}).get("asn"):
        item = _deny_alone(item)                          # 🚀: its network on the deny list by herself (sec_egress)
    if item["kind"] in ("egress_new", "egress_upload"):
        item = _egress_alone(item)                        # 🚀: learnt, or denied, by herself (sec_egress_watch)
        if item.get("status") == "closed":
            return {"id": item["id"], "severity": item["severity"], "learnt": True}
    from aurora import sec_quiet
    quiet = sec_quiet.is_quiet(cfg, item)
    if quiet:                                             # a pattern the owner quieted (sec_quiet): kept, low, not said
        item = Incidents(cfg).update(item["id"], severity="low", quiet=quiet)
        return {"id": item["id"], "severity": "low", "quiet": quiet}
    who = f"{name} ({item['source']})" if name else item["source"]
    if not (name and item["severity"] == "low"):          # a known device's routine traffic: in the list, no alert
        note("sentinel", "incident", {"id": item["id"], "kind": item["kind"], "source": item["source"],
                                      "severity": item["severity"], "title": f"{item['kind']} · {who}"})
    defend(item)
    if item["kind"] == "honeypot":                        # a decoy touched: off this machine at once (sec_hostfw)
        import threading

        def keep_out():
            from aurora import sec_hostfw
            r = sec_hostfw.block(cfg, item["source"], f"esca toccata (porta {item.get('detail', {}).get('port')})")
            Incidents(cfg).update(item["id"], hostfw="blocked" if r.get("ok") else f"not blocked: {r.get('why')}")
            if r.get("ok"):
                note("security", "hostfw.block", {"title": f"🧱 {item['source']} bloccato sul computer di Aurora", "text": "esca toccata"})
        threading.Thread(target=keep_out, name="hostfw", daemon=True).start()
    # a known device's routine needs no inquiry — but one of them reaching a threat feed's address does (M161: those
    # were never looked at, the device being known)
    if cfg["AURORA_SENTINEL_INVESTIGATE"] and (not name or outbound):
        def job(q, emit, run_id):
            from aurora.kno_answer import Answer
            from aurora.sec_incidents import investigate
            text = investigate(pipeline(), plugin_host(), item, emit, cfg)
            return Answer(run_id, q, text, False, mode="agent")
        start_run(f"[incident] {item['kind']} {item['source']}", origin="sentinel", job=job)
    return {"id": item["id"], "severity": item["severity"]}


def destination_of(incident: dict) -> dict:
    """For a threat match from inside (a device at home → the Internet): the address it reached, what the public lists
    and the providers say of it, its DNS name. {} for anything else."""
    import re
    from aurora import sec_intel, sec_sentinel
    if not incident.get("internal") or incident.get("kind") != "ips_alert":
        return {}
    m = next((re.search(r'dst_ip="?([0-9a-fA-F.:]+)', s) for s in incident.get("samples") or [] if "dst_ip" in s), None)
    dst = m.group(1) if m else ""
    if not dst or sec_sentinel.is_private(dst):
        return {}
    out = {"destination": dst}
    hits = sec_intel.lookup(cfg, dst)
    if hits:
        out["destination_lists"] = hits
    provider = sec_intel.shared(cfg, dst)
    if provider:
        out["destination_provider"] = provider             # a cloud's address: many services behind it
    feed = re.search(r'threatfeed="([^"]+)"', " ".join(incident.get("samples") or []))
    if feed:
        out["destination_feed"] = feed.group(1)
    try:
        import socket
        socket.setdefaulttimeout(2)
        out["destination_name"] = socket.gethostbyaddr(dst)[0]
    except OSError:
        pass
    finally:
        import socket as _s
        _s.setdefaulttimeout(None)
    return out


def defend(item: dict) -> None:
    """Autonomous defence (sec_defence): the source blocked now when every limit allows it, told either way."""
    import threading
    from aurora import sec_defence, sec_fwapi
    from aurora.sec_incidents import Incidents
    ok, why = sec_defence.decide(cfg, item)
    if not ok:
        if why != "mode":
            Incidents(cfg).update(item["id"], defence=why)
        return

    def run():
        try:
            out = sec_defence.act(cfg, item)
            Incidents(cfg).update(item["id"], defence="blocked", blocked_until=out["until"])
            note("security", "defence.block", {"title": f"🛡️ {item['source']} bloccato da Aurora",
                                               "text": f"{item['kind']} · {item['severity']} · {cfg['AURORA_DEFENCE_HOURS']} h"})
        except sec_fwapi.FirewallAPIError as e:
            Incidents(cfg).update(item["id"], defence=f"failed: {e}")
            note("security", "defence.failed", {"title": f"⚠️ {item['source']} non bloccato", "text": str(e)[:180]})
    threading.Thread(target=run, name="defence", daemon=True).start()


@router.get("/v1/aurora/incidents", dependencies=[Depends(admin_only)])
def incidents(status: str | None = None, archived: bool = False) -> list[dict]:
    from aurora.sec_incidents import Incidents
    return Incidents(cfg).list(status, archived)[:200]


@router.post("/v1/aurora/incidents/archive-closed", dependencies=[Depends(admin_only)])
def incidents_archive_closed() -> dict:
    """The owner tidies the Security page: closed incidents archived (kept for the reports)."""
    from aurora.sec_incidents import Incidents
    n = Incidents(cfg).archive_closed()
    log.info("audit: owner archived %d closed incidents", n)
    return {"archived": n}


_score: dict = {}


@router.get("/v1/aurora/security/scorecard", dependencies=[Depends(admin_only)])
async def security_scorecard(again: bool = False) -> dict:
    """The autopilot's scorecard (sec_scorecard, roadmap 81): kept 10 minutes (the firewall's log is read for silences)."""
    from aurora import sec_scorecard
    if again or not _score or time.time() - _score.get("at", 0) > 600:
        _score.update(at=time.time(), value=await asyncio.to_thread(sec_scorecard.scorecard, cfg))
    return _score["value"]


@router.post("/v1/aurora/incidents/{incident_id}/verdict", dependencies=[Depends(admin_only)])
async def incident_verdict(incident_id: str, request: Request) -> dict:
    """The owner's judgement of an incident: right, overrated (true, but less serious than said), false_alarm or
    unsure (and a note) — the scorecard counts them."""
    from aurora import sec_scorecard
    from aurora.sec_incidents import Incidents
    body = await request.json()
    verdict = str(body.get("verdict", ""))
    if verdict not in sec_scorecard.VERDICTS:
        raise HTTPException(status_code=422, detail=f"verdict: one of {', '.join(sec_scorecard.VERDICTS)}")
    try:
        item = Incidents(cfg).update(incident_id, verdict=verdict, verdict_note=str(body.get("note", ""))[:300],
                                     verdict_at=time.time())
    except StopIteration:
        raise HTTPException(status_code=404, detail="unknown incident")
    _score.clear()
    log.info("audit: incident %s judged %s by the owner", incident_id, verdict)
    from aurora import sec_quiet                          # the verdict put to use: a pattern proposed, or woken
    said = sec_quiet.after_verdict(cfg, Incidents(cfg).list(), item)
    if said and said.get("propose") and not _quiet_alone(Incidents(cfg).list()):   # 🚀: quieted by herself, told
        x = said["propose"]
        note("security", "quiet.propose", {"title": "🔇 Silenzio questo allarme su questo dispositivo?",
             "text": f"«{x['label']}»: {x['false_alarm']} falsi allarmi e {x['right']} giusti su {x['judged']} giudizi. "
                     "Rispondi nella pagina Sicurezza."})
    elif said and said.get("woke"):
        log.info("audit: incidents «%s» awake again: judged right", said["woke"])
        note("security", "quiet.woke", {"title": "🔔 Tipo di allarme riattivato", "text": f"«{said['label']}»: l'hai giudicato giusto, torna ad avvisarti."})
    return {"id": incident_id, "verdict": verdict, **({"quiet": said} if said else {})}


def _egress_alone(item: dict) -> dict:
    """A way out of a service never seen, or a file going out (sec_egress_watch). With security at 🚀: a new network
    met while a run was working is learnt (the incident closed, low, in her ledger); one met with nothing running, or
    a file going out, is denied by herself — unless the network is shared (a cloud's, a CDN's: denying it cuts off
    half the web), then it waits for the owner like at 🤝 or 🔒."""
    from aurora import sec_egress_watch, sys_autonomy
    from aurora.sec_incidents import Incidents
    if sys_autonomy.levels(cfg).get("security") != 2:
        return item
    d = item["detail"]
    if item["kind"] == "egress_new" and d.get("busy"):
        sec_egress_watch.decide(cfg, d["service"], d["key"], "legit")
        sys_autonomy.log(cfg, "security", f"learnt {d['service']} → {d['key']} {d.get('holder', '')} (met during a run)")
        note("security", "egress.learnt", {"title": "🌐 Ho imparato una nuova uscita",
             "text": f"{d.get('title', '')}: incontrata durante un lavoro, la considero legittima. Se non lo è: pagina "
                     "Sicurezza → Uscite."})
        return Incidents(cfg).update(item["id"], status="closed", severity="low", closed=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                                     decided="learnt by Aurora")
    if d.get("shared") or not d.get("asn"):
        return item
    sec_egress_watch.decide(cfg, d["service"], d["key"], "denied")
    return _deny_alone({**item, "detail": {**d, "destination": d.get("destination")}})


def _deny_alone(item: dict) -> dict:
    """The local model reached out (sec_egress.ModelWatch): with security at 🚀 on the Autonomy page its network goes on
    the deny list by herself — the sentinel watches it at once, the units take it at their next install —, written to
    her ledger and told; at 🤝 or 🔒 the incident's button waits for the owner."""
    from aurora import sec_egress, sys_autonomy, sys_config
    from aurora.sec_incidents import Incidents
    if sys_autonomy.levels(cfg).get("security") != 2:
        return item
    d = item["detail"]
    listed = sec_egress.add_deny(cfg, int(d["asn"]))
    sys_config.write_env(sys_config.env_file_path(), {"AURORA_EGRESS_DENY_ASNS": ",".join(listed)})
    cfg.values["AURORA_EGRESS_DENY_ASNS"] = listed
    sec_egress.refresh(cfg, force=True)
    sys_autonomy.log(cfg, "security", f"AS{d['asn']} {d.get('holder', '')} on the deny list: {d.get('title', '')}")
    log.warning("audit: AS%s added to the deny list by Aurora (security 🚀): %s", d["asn"], d.get("title", ""))
    note("security", "egress.denied", {"title": "🚫 Ho messo una rete in blacklist",
         "text": f"{d.get('title', '')} → AS{d['asn']} {d.get('holder', '')} è in blacklist e la sentinella la "
                 "sorveglia. Perché anche i servizi non possano raggiungerla: reinstalla le unit."})
    return Incidents(cfg).update(item["id"], deny="added by Aurora")


def _quiet_alone(items: list[dict]) -> list[str]:
    """With security at 🚀 on the Autonomy page (owner, 27 Oct: «l'obiettivo è arrivare ad avere aurora che prende
    decisioni in modo indipendente»), the patterns that qualify are quieted by herself — on this machine only, so
    level B is not asked —, written to her ledger and told, with the way back; at 🤝 or 🔒 they wait for the owner."""
    from aurora import sec_quiet, sys_autonomy
    if sys_autonomy.levels(cfg).get("security") != 2:
        return []
    done = []
    for x in sec_quiet.proposals(cfg, items):
        sec_quiet.answer(cfg, x["pattern"], "quiet", sec_quiet.tally(items)[x["pattern"]], x["name"])
        sys_autonomy.log(cfg, "security", f"quieted «{x['label']}»: {x['false_alarm']} false alarms, {x['right']} right")
        note("security", "quiet.auto", {"title": "🔇 Ho silenziato un allarme su un dispositivo",
             "text": f"«{x['label']}»: {x['false_alarm']} falsi allarmi e {x['right']} giusti su {x['judged']} tuoi "
                     "giudizi. Restano nell'elenco come bassi; si riattiva dalla pagina Sicurezza, o da sé con un 👍."})
        log.info("audit: incidents «%s» quieted by Aurora (security 🚀)", x["pattern"])
        done.append(x["pattern"])
    return done


@router.get("/v1/aurora/incidents/quiet", dependencies=[Depends(admin_only)])
def incidents_quiet(lang: str = "it") -> dict:
    """The patterns proposed for quiet (the owner's verdicts, sec_quiet) and the ones quiet now."""
    from aurora import sec_quiet, sys_autonomy
    from aurora.sec_incidents import Incidents
    items = Incidents(cfg).list()
    if moved := sec_quiet.by_kind(cfg, items):            # C407: the answers given to a kind alone, made per device
        log.info("audit: incidents quiet per device now (C407): %s", ", ".join(moved))
    _quiet_alone(items)                                   # raised to 🚀 since a proposal: decided now
    return {"alone": sys_autonomy.levels(cfg).get("security") == 2, "proposals": sec_quiet.proposals(cfg, items, lang), "quiet": sec_quiet.quiet_list(cfg, lang),
            "rule": {"false_alarm": sec_quiet.PROPOSE_FA, "right_share": sec_quiet.PROPOSE_RIGHT, "days": sec_quiet.WINDOW_DAYS}}


@router.post("/v1/aurora/incidents/quiet", dependencies=[Depends(admin_only)])
async def incidents_quiet_answer(request: Request) -> dict:
    """The owner's answer on a pattern: quiet, declined or awake."""
    from aurora import sec_quiet
    from aurora.sec_incidents import Incidents
    body = await request.json()
    p, state = str(body.get("pattern", "")), str(body.get("state", ""))
    items = Incidents(cfg).list()
    counts = sec_quiet.tally(items).get(p)
    if not p or (state == "quiet" and counts is None):
        raise HTTPException(status_code=404, detail="unknown pattern")
    try:
        out = sec_quiet.answer(cfg, p, state, counts, sec_quiet.names(items).get(p, ""))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    log.info("audit: incidents «%s» set %s by the owner", p, state)
    return out


@router.post("/v1/aurora/incidents/{incident_id}/close", dependencies=[Depends(admin_only)])
def close_incident(incident_id: str) -> dict:
    from aurora.sec_incidents import Incidents
    try:
        Incidents(cfg).update(incident_id, status="closed", closed=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    except StopIteration:
        raise HTTPException(status_code=404, detail="unknown incident")
    log.info("audit: incident %s closed by the owner", incident_id)
    return {"id": incident_id, "status": "closed"}


# names of sibling modules, looked up only when called: imported last, so that modules that use each
# other (routines, forge, agents) load in any order
from .system import status  # noqa: E402
