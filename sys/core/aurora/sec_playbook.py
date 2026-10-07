# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The security officer's view (owner, 2026-10-07: "a real cyber-security capability, at CISO level"): signals joined
by device, a playbook for each scenario, a register of the risks still open.

- correlate(): the hunt's findings (sec_hunt) and the open incidents (sentinel, baseline) grouped by the device or
  the outside address they are about. Two different signals on one device of the house, one at least medium, make it
  a suspect: what alone may be a program's habit, together is a pattern.
- scenario(): which playbook a group of signals calls for — intrusion from outside, a compromised device, data
  leaving, the firewall's administration touched.
- PLAYBOOKS: the steps a responder follows, in order, each saying whether Aurora can do it (and with which tool) or
  the owner must.
- register(): the risks of the configuration (sec_audit) and the scenarios found, by severity — what the weekly
  report counts.
Read only: an action of a playbook is a change planned by sec_fwwrite and approved by the owner.
"""
from __future__ import annotations

from collections import defaultdict

from .sec_sentinel import is_private

RANK = {"high": 0, "medium": 1, "low": 2}
ICON = {"high": "🔴", "medium": "🟠", "low": "🟡"}

DEVICE = {"beacon", "sweep", "atp_out", "domain", "behaviour:new_country", "behaviour:new_port", "behaviour:upload",
          "behaviour:new_device", "ips_alert"}
OUTSIDE = {"atp_in", "port_scan", "deny_burst", "auth_fail", "honeypot", "ips_alert"}
ADMIN = {"admin_fail", "admin_outside", "admin_changes"}
FIREWALL = "firewall"                                     # the group of the firewall's own administration

PLAYBOOKS = {
    "intrusion": {
        "title": "Tentativo di intrusione dall'esterno",
        "steps": [("Bloccare la sorgente sul firewall (a tempo)", "Aurora: difesa automatica o ⛔ sull'incidente"),
                  ("Capire quale servizio pubblicato è preso di mira", "Aurora: firewall_audit"),
                  ("Proteggere quel servizio: IPS, log, filtro per paese", "Aurora: firewall_plan_harden, con la tua approvazione"),
                  ("Se il servizio non serve da fuori, ritirarlo", "Aurora: firewall_plan_unpublish (se è suo) o tu dal firewall"),
                  ("Aggiornare il software del server esposto", "tu")]},
    "compromised": {
        "title": "Dispositivo della casa forse compromesso",
        "steps": [("Isolarlo: quarantena sul firewall", "Aurora: firewall_plan_quarantine, con la tua approvazione"),
                  ("Capire quale programma fa il traffico (processi, app installate di recente)", "tu, sul dispositivo"),
                  ("Cambiare le password usate da quel dispositivo, da un altro dispositivo", "tu"),
                  ("Scansione antimalware o ripristino del dispositivo", "tu"),
                  ("Fine della quarantena e una settimana di osservazione", "Aurora: firewall_plan_release, poi la caccia ogni 6 ore")]},
    "leak": {
        "title": "Dati che escono in modo insolito",
        "steps": [("Vedere verso dove e quanto (paese, dominio, volume)", "Aurora: threat_hunt e il comportamento del dispositivo"),
                  ("Se non è un backup o un caricamento tuo: quarantena", "Aurora: firewall_plan_quarantine"),
                  ("Capire quali dati: account cloud, sincronizzazioni, app", "tu"),
                  ("Cambiare le credenziali degli account coinvolti", "tu")]},
    "check": {
        "title": "Da controllare",
        "steps": [("Guardare il segnale: quale app o servizio lo spiega", "tu, con i dettagli di Aurora"),
                  ("Se non ha spiegazione, o se si ripete, trattarlo come un dispositivo compromesso", "Aurora te lo dice alla caccia successiva")]},
    "admin": {
        "title": "L'amministrazione del firewall è stata toccata",
        "steps": [("Verificare che login e modifiche siano tuoi", "tu, con l'elenco di Aurora"),
                  ("Se non lo sono: cambiare subito la password dell'amministratore e dell'utente API", "tu"),
                  ("Chiudere l'amministrazione da WAN; solo LAN o VPN", "tu (l'audit dice se è aperta)"),
                  ("Annullare le modifiche non tue", "tu dal firewall; Aurora annulla solo le sue (firewall_revert)")]},
}


def _kind(item: dict) -> str:
    return str(item.get("kind", ""))


def correlate(findings: list[dict], incidents: list[dict]) -> list[dict]:
    """[{"who", "internal", "signals": [...], "kinds", "severity", "scenario"}] most severe first."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for f in findings:
        # the firewall's administration is one subject, not the device the owner happened to use (M134: the owner's
        # own edits from the phone made the phone a suspect)
        who = FIREWALL if f["kind"] in ADMIN else str(f.get("source", ""))
        groups[who].append({"kind": f["kind"], "severity": f["severity"], "title": f["title"], "from": "caccia"})
    for i in incidents:
        if i.get("status") != "open":
            continue
        groups[str(i.get("source", ""))].append({"kind": _kind(i), "severity": i.get("severity", "low"),
                                                 "title": (i.get("detail") or {}).get("title") or _kind(i), "from": "incidente"})
    out = []
    for who, signals in groups.items():
        if not who:
            continue
        kinds = sorted({s["kind"] for s in signals})
        sev = min((s["severity"] for s in signals), key=lambda s: RANK.get(s, 2))
        internal = who != FIREWALL and is_private(who)
        # only signals worth a look count: a false positive judged low, or a known device's routine, is no evidence
        strong = {s["kind"] for s in signals if RANK.get(s["severity"], 2) <= 1
                  and (s["kind"] in DEVICE or s["kind"].startswith("behaviour:"))}
        if internal and len(strong) >= 2:
            sev = "high"                                  # two different signals on one device: a pattern
        scene = scenario(kinds, internal) if who != FIREWALL else ("admin" if RANK.get(sev, 2) <= 1 else "")
        if scene in ("compromised", "leak") and sev != "high":
            scene = "check"                               # one medium signal alone: to look at, not a compromise
        out.append({"who": who, "internal": internal, "signals": signals, "kinds": kinds, "severity": sev,
                    "scenario": scene})
    return sorted(out, key=lambda g: (RANK.get(g["severity"], 2), -len(g["signals"])))


def scenario(kinds: list[str], internal: bool) -> str:
    ks = set(kinds)
    if internal and "behaviour:upload" in ks:
        return "leak"
    if internal and (ks & DEVICE):
        return "compromised"
    if not internal and (ks & OUTSIDE or any(k.startswith("rule:") for k in ks)):
        return "intrusion"
    return ""


def register(audit: dict | None, groups: list[dict]) -> list[dict]:
    """The open risks: the configuration's (audit) and the scenarios on devices or sources, most severe first."""
    risks = [{"severity": f["severity"], "what": f["title"], "fix": f["fix"], "from": "configurazione"}
             for f in (audit or {}).get("findings", []) if f["severity"] != "low"]
    for g in groups:
        if g["scenario"] and g["scenario"] != "check" and RANK.get(g["severity"], 2) <= 1:
            who = "amministrazione del firewall" if g["who"] == FIREWALL else g["who"]
            risks.append({"severity": g["severity"], "what": f"{PLAYBOOKS[g['scenario']]['title']}: {who}",
                          "fix": PLAYBOOKS[g["scenario"]]["steps"][0][0], "from": "attività"})
    return sorted(risks, key=lambda r: RANK.get(r["severity"], 2))


def text(groups: list[dict], risks: list[dict], names: dict[str, str] | None = None, limit: int = 6) -> str:
    names = names or {}
    label = (lambda ip: "amministrazione del firewall" if ip == FIREWALL else (f"{names[ip]} ({ip})" if ip in names else ip))
    lines = ["🧭 **Quadro della sicurezza**"]
    if risks:
        lines.append(f"\n**Registro dei rischi aperti** ({len(risks)})")
        lines += [f"{ICON.get(r['severity'], '•')} {r['what']} — ➜ {r['fix']}" for r in risks[:12]]
    else:
        lines.append("\nNessun rischio aperto di gravità media o alta.")
    shown = [g for g in groups if g["scenario"] and RANK.get(g["severity"], 2) <= 1][:limit]
    for g in shown:
        pb = PLAYBOOKS[g["scenario"]]
        lines.append(f"\n{ICON[g['severity']]} **{pb['title']}: {label(g['who'])}**")
        lines += [f"   • {s['title']} ({s['from']})" for s in g["signals"][:5]]
        lines.append("   Cosa fare:")
        lines += [f"   {n}. {step} — {who}" for n, (step, who) in enumerate(pb["steps"], 1)]
    return "\n".join(lines)
