# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The firewall's configuration judged as a security officer would (owner, 2026-10-07: "a real cyber-security
capability, at CISO level"). Read only: each finding says what, why it matters and the fix; the fix that Aurora can
apply herself (an IPS policy on a published service, its log) is offered by sec_fwwrite with the owner's approval.

Checks, deterministic, on the neutral model (sec_fwmodel: any dialect; a rule's own IPS where the dialect has one,
else the firewall's engine):
  exposed        a rule that lets the Internet (zone WAN) in: which service and port, from where, with or without
                 intrusion prevention and log; an IPS policy that exists for it but is not applied is named
  admin_wan      the firewall's own administration (HTTPS, SSH) reachable from the WAN zone
  wan_services   the firewall's other services on the WAN zone (VPN portals…): fine when meant, said once
  atp            Advanced Threat Protection off, or logging without dropping
  login          the administrator's login: lockout after failures, password complexity
  blocklist      Aurora's blocking group is applied by an enabled rule, and before the rules that let the Internet in
  syslog         the firewall sends its syslog here, with the threat events (IPS, ATP) on
  any_any        an enabled Accept rule with no zone on either side
  no_ips_out     rules towards the Internet with no intrusion prevention (counted, low)
  disabled       disabled rules (counted: housekeeping)
"""
from __future__ import annotations

from . import sec_fwmodel, sys_config
from .sys_lang import say as _t   # each sentence in the reader's language (C526)

RANK = {"high": 0, "medium": 1, "low": 2}
ICON = {"high": "🔴", "medium": "🟠", "low": "🟡"}


def _f(fid: str, severity: str, title: str, why: str, fix: str, obj: str = "", **extra) -> dict:
    return {"id": fid, "severity": severity, "title": title, "why": why, "fix": fix, "object": obj, **extra}


def _m(x: dict, group: str = "") -> dict:
    """The neutral model (sec_fwmodel); the first dialect's configuration is turned into it."""
    return x if sec_fwmodel.is_model(x) else sec_fwmodel.of_sophos(x, group)


def _ips_for(m: dict, rule: dict) -> str:
    """An IPS policy whose name is in the rule's name or services (e.g. «Plex» for «TNas_Plex»), or ""."""
    names = [rule["name"].lower()] + [s.lower() for s in rule["services"]] + [n.lower() for n in rule["dst_nets"]]
    for n in m.get("ips_policies", []):
        if len(n) >= 3 and any(n.lower() in x for x in names):
            return n
    return ""


def _no_ips(m: dict, r: dict) -> bool:
    """No intrusion prevention on this traffic: the rule's own policy none, or — where a rule has no such field — the
    firewall's engine not blocking."""
    # an engine not read (state None) is not judged: said by threat(), never guessed here
    return r["ips"] in ("None", "") if r["ips"] is not None else m["threat"].get("state") in ("off", "log")


def exposed(conf: dict) -> list[dict]:
    m = _m(conf)
    out = []
    for r in m["rules"]:
        if not r["enabled"] or r["action"] != "Accept" or "WAN" not in r["src_zones"] or r["system"] or r["to_self"]:
            continue
        if r["dst_zones"] and set(r["dst_zones"]) <= {"WAN"}:
            continue
        ports = r["ports"] or ([_t("ogni servizio", "every service")] if not r["services"] else r["services"])
        nats = [n for n in m["nat"] if n["enabled"] and (set(n["services"]) & set(r["services"]) or n.get("rule") == r["name"])]
        nat = [n["name"] for n in nats]
        # the origin may be limited on the NAT rule instead (the owner, 9 Oct: Plex «Italy» on the DNAT — the audit
        # kept saying «open to the whole Internet»): the port forwards from outside, all with an original source,
        # limit who reaches the service
        outside = [n for n in nats if n["outside"]]
        nat_src = sorted({x for n in outside for x in n["sources"]})
        limited_by_nat = bool(outside) and all(n["sources"] for n in outside)
        policy = _ips_for(m, r)
        problems, fixes = [], []
        if _no_ips(m, r):
            problems.append(_t("nessuna prevenzione delle intrusioni (IPS)", "no intrusion prevention (IPS)"))
            if r["ips"] is None:
                fixes.append(_t(f"attivare la prevenzione delle intrusioni del firewall ({m['threat'].get('what') or 'IPS'})", f"turn on the firewall's intrusion prevention ({m['threat'].get('what') or 'IPS'})"))
            else:
                fixes.append(_t(f"applicare la policy IPS «{policy}», che esiste già ma non è usata qui", f"apply the IPS policy «{policy}», which exists already but is not used here") if policy
                             else _t("applicare una policy IPS adatta al servizio", "apply an IPS policy that suits the service"))
        if not r["log"]:
            problems.append(_t("il traffico non è registrato", "the traffic is not logged"))
            fixes.append(_t("attivare il log della regola, così Aurora vede chi entra", "turn on the rule's log, so Aurora sees who comes in"))
        origin = r["src_nets"] or (nat_src if limited_by_nat else [])
        if not origin:
            problems.append(_t("aperta a tutta Internet", "open to the whole Internet"))
            fixes.append(_t("limitare l'origine (paesi o indirizzi) se il servizio serve solo ad alcuni", "limit the origin (countries or addresses) if the service is meant for a few"))
        sev = "high" if _no_ips(m, r) and not origin else ("medium" if problems else "low")
        out.append(_f(f"exposed:{r['name']}", sev, _t(f"Servizio pubblicato su Internet: {', '.join(ports)}", f"Service published on the Internet: {', '.join(ports)}"),
                      _t(f"La regola «{r['name']}» lascia entrare da Internet verso {', '.join(r['dst_zones'] or r['dst_nets']) or 'ogni zona'}",
                         f"The rule «{r['name']}» lets the Internet in towards {', '.join(r['dst_zones'] or r['dst_nets']) or 'every zone'}")
                      + (f" (NAT: {', '.join(nat)})" if nat else "") + (": " + "; ".join(problems) if problems else
                                                                          _t(": con IPS e log attivi", ": with IPS and log on"))
                      + (_t("; origine limitata a ", "; origin limited to ") + ", ".join(origin)
                         + (_t(" dal NAT", " by the NAT") if not r["src_nets"] else "") if origin else ""),
                      "; ".join(fixes) or _t("nulla: va bene così se il servizio deve essere pubblico", "nothing: fine as it is if the service must be public"), r["name"],
                      rule=r["name"], ports=ports, ips_policy=policy, ips=r["ips"], log=r["log"], origin=origin,
                      origin_from="rule" if r["src_nets"] else ("nat" if limited_by_nat else "")))
    return out


def zones(conf: dict) -> list[dict]:
    m = _m(conf)
    out, where = [], m.get("wan_zone", "WAN")
    if m["wan_admin"]:
        out.append(_f("admin_wan", "high", _t(f"Amministrazione del firewall raggiungibile da Internet ({', '.join(m['wan_admin'])})", f"The firewall's administration can be reached from the Internet ({', '.join(m['wan_admin'])})"),
                      _t("Chi trova la pagina di login può tentare le password o sfruttare una vulnerabilità del pannello", "Whoever finds the login page can try passwords or exploit a vulnerability of the panel"),
                      _t("togliere HTTPS e SSH dalla zona WAN; amministrare da LAN o dalla VPN", "remove HTTPS and SSH from the WAN zone; administer from the LAN or the VPN"), where))
    if m["wan_services"]:
        out.append(_f("wan_services", "low", _t(f"Servizi del firewall aperti su Internet: {', '.join(m['wan_services'])}", f"Services of the firewall open on the Internet: {', '.join(m['wan_services'])}"),
                      _t("Normale se usati (per esempio la VPN da fuori); ogni servizio aperto è una porta in più", "Normal if used (the VPN from outside, for example); every open service is one more door"),
                      _t("tenerli solo se servono; con un filtro per paese o la VPN con autenticazione a due fattori", "keep them only if needed; with a country filter, or the VPN with two-factor authentication"), where))
    return out


def threat(conf: dict) -> list[dict]:
    m = _m(conf)
    out, th = [], m["threat"]
    if th.get("what") == "ATP":                            # the first dialect's engine, in its own words
        if th["state"] == "off":
            out.append(_f("atp", "high", _t("Protezione dalle minacce avanzate (ATP) spenta", "Advanced Threat Protection (ATP) is off"),
                          _t("Il firewall non riconosce i dispositivi che parlano con server di malware noti", "The firewall does not recognise the devices that talk to known malware servers"),
                          _t("attivare ATP con la politica «Log and Drop»", "turn ATP on with the «Log and Drop» policy")))
        elif th["state"] == "log":
            out.append(_f("atp", "medium", _t(f"ATP solo in registrazione ({th.get('policy')})", f"ATP only logs ({th.get('policy')})"),
                          _t("Il traffico verso i server malevoli viene visto ma non fermato", "The traffic towards malicious servers is seen but not stopped"), _t("politica «Log and Drop»", "the «Log and Drop» policy")))
    elif th.get("state") == "off":
        out.append(_f("ids", "high", _t(f"Prevenzione delle intrusioni spenta ({th['what']})", f"Intrusion prevention is off ({th['what']})"),
                      _t("Il firewall non ispeziona il traffico: attacchi noti e dispositivi infetti passano senza essere visti", "The firewall does not inspect the traffic: known attacks and infected devices pass unseen"),
                      _t(f"attivare {th['what']} in modalità di blocco (IPS) sulla WAN", f"turn {th['what']} on in blocking mode (IPS) on the WAN")))
    elif th.get("state") == "log":
        out.append(_f("ids", "medium", _t(f"{th['what']} solo in rilevamento (IDS)", f"{th['what']} only detects (IDS)"),
                      _t("Gli attacchi vengono visti ma non fermati", "The attacks are seen but not stopped"), _t("passare alla modalità IPS (blocco)", "switch to IPS mode (blocking)")))
    if m["login"].get("lockout") is False:
        out.append(_f("login", "medium", _t("Nessun blocco dopo i login falliti", "No lockout after failed logins"),
                      _t("Le password dell'amministratore si possono provare senza limite", "The administrator's passwords can be tried without limit"), _t("attivare il blocco del login", "turn on the login lockout")))
    if m["login"].get("complexity") is False:
        out.append(_f("login_pw", "low", _t("Complessità delle password non richiesta", "Password complexity is not required"), _t("Password deboli accettate", "Weak passwords are accepted"),
                      _t("attivare il controllo di complessità", "turn on the complexity check")))
    return out


def _unread(part: str, what: str, m: dict) -> list[dict]:
    """A part the firewall did not give: not judged as absent (an empty list is not "none configured")."""
    name, err = sec_fwmodel.error_of(m, part)
    if err is None:
        return []
    return [_f(f"unread:{name}", "medium", _t(f"Non verificato: {what} ({name} non letto dal firewall)", f"Not verified: {what} ({name} not read from the firewall)"),
               _t(f"La lettura via API è fallita: {err}", f"Reading through the API failed: {err}"),
               _t("controllare indirizzo, utente e password dell'API e che l'indirizzo di Aurora sia ammesso all'API", "check the API's address, user and password, and that Aurora's address is allowed to use the API"), name)]


def blocklist(conf: dict, group: str) -> list[dict]:
    m = _m(conf, group)
    unread = _unread("rules", _t("la regola dei blocchi di Aurora", "the rule of Aurora's blocks"), m)
    if unread:
        return unread
    group = m.get("block_object") or group
    rules = m["rules"]
    idx = next((i for i, r in enumerate(rules) if r["enabled"] and group in r["src_nets"]
                and r["action"] in ("Drop", "Reject")), None)
    if idx is None:
        return [_f("blocklist", "high", _t(f"I blocchi di Aurora non hanno effetto: nessuna regola attiva usa il gruppo «{group}»", f"Aurora's blocks have no effect: no enabled rule uses the group «{group}»"),
                   _t("Aurora aggiunge gli indirizzi al gruppo, ma senza una regola Drop/Reject il firewall li lascia passare", "Aurora adds the addresses to the group, but without a Drop/Reject rule the firewall lets them through"),
                   _t(f"una regola in cima: origine «{group}», azione Drop", f"a rule at the top: source «{group}», action Drop"), group)]
    before = [r["name"] for r in rules[:idx] if r["enabled"] and r["action"] == "Accept" and "WAN" in r["src_zones"]
              and not r["system"]]
    if before:
        return [_f("blocklist_order", "medium", _t("La regola dei blocchi viene dopo regole che lasciano entrare da Internet", "The blocking rule comes after rules that let the Internet in"),
                   _t(f"Un indirizzo bloccato passa comunque da: {', '.join(before)}", f"A blocked address still gets in through: {', '.join(before)}"),
                   _t(f"spostare la regola dei blocchi prima di {before[0]}", f"move the blocking rule before {before[0]}"), group)]
    return []


def syslog(conf: dict, own: set[str]) -> list[dict]:
    m = _m(conf)
    unread = _unread("syslog", _t("l'invio del syslog ad Aurora", "the syslog sent to Aurora"), m)
    if unread:
        return unread
    mine = [s for s in m["syslog"] if s.get("address") in own]
    if not mine:
        return [_f("syslog", "high", _t("Il firewall non manda il syslog ad Aurora", "The firewall does not send its syslog to Aurora"),
                   _t("Senza i log Aurora non vede attacchi, intrusioni né dispositivi sospetti", "Without the logs Aurora sees no attacks, intrusions or suspicious devices"),
                   _t("aggiungere Aurora tra i server syslog (formato standard, porta della sentinella)", "add Aurora to the syslog servers (standard format, the sentinel's port)"))]
    if mine[0]["threats_off"]:
        return [_f("syslog_threats", "medium", _t(f"Eventi di minaccia non inviati ad Aurora: {', '.join(mine[0]['threats_off'])}", f"Threat events not sent to Aurora: {', '.join(mine[0]['threats_off'])}"),
                   _t("Aurora non vede una parte degli allarmi", "Aurora does not see a part of the alarms"), _t("attivarli nel server syslog «", "turn them on in the syslog server «") + str(mine[0].get("name")) + "»")]
    return []


def rules_hygiene(conf: dict) -> list[dict]:
    rules = [r for r in _m(conf)["rules"] if not r["system"]]
    out = []
    for r in rules:
        if r["enabled"] and r["action"] == "Accept" and not r["src_zones"] and not r["dst_zones"] and not r["src_nets"]:
            out.append(_f(f"any_any:{r['name']}", "medium", _t(f"Regola che accetta tutto: «{r['name']}»", f"A rule that accepts everything: «{r['name']}»"),
                          _t("Nessuna zona né rete: lascia passare traffico che nessuno ha pensato", "No zone and no network: it lets through traffic nobody thought of"),
                          _t("indicare zone di origine e destinazione", "name the source and destination zones"), r["name"]))
    no_ips = [r["name"] for r in rules if r["enabled"] and r["action"] == "Accept" and "WAN" in r["dst_zones"]
              and r["ips"] in ("None", "")]
    if no_ips:
        out.append(_f("no_ips_out", "low", _t(f"{len(no_ips)} regole verso Internet senza IPS", f"{len(no_ips)} rules towards the Internet without IPS"),
                      _t("Un dispositivo infetto che parla verso l'esterno non viene ispezionato da queste regole", "An infected device talking to the outside is not inspected by these rules"),
                      _t("una policy IPS «LAN TO WAN» sulle regole generali", "an IPS policy «LAN TO WAN» on the general rules"), ", ".join(no_ips[:8])))
    off = [r["name"] for r in rules if not r["enabled"]]
    if off:
        out.append(_f("disabled", "low", _t(f"{len(off)} regole disattivate", f"{len(off)} disabled rules"), _t("Regole dimenticate confondono chi legge la configurazione", "Forgotten rules confuse whoever reads the configuration"),
                      _t("cancellarle se non servono più", "delete them if no longer needed"), ", ".join(off[:8])))
    return out


def run(cfg: sys_config.Config, conf: dict | None = None) -> dict:
    """{"findings": [...] most severe first, "counts": {severity: n}, "errors": {part: error}, "kind"}: the firewall of
    `cfg` (sec_firewalls.view for one of many), any dialect."""
    from . import sec_fwapi
    group = str(cfg["AURORA_FIREWALL_BLOCK_GROUP"])
    m = sec_fwmodel.read(cfg) if conf is None else _m(conf, group)
    findings = (exposed(m) + zones(m) + threat(m) + blocklist(m, group)
                + syslog(m, sec_fwapi._own_addresses()) + rules_hygiene(m))
    findings.sort(key=lambda f: RANK[f["severity"]])
    counts = {s: sum(1 for f in findings if f["severity"] == s) for s in RANK}
    return {"findings": findings, "counts": counts, "errors": m.get("_errors", {}), "kind": m["kind"]}


def text(result: dict) -> str:
    c = result["counts"]
    lines = [_t(f"🛡️ Audit del firewall: {c['high']} 🔴 · {c['medium']} 🟠 · {c['low']} 🟡", f"🛡️ Firewall audit: {c['high']} 🔴 · {c['medium']} 🟠 · {c['low']} 🟡")]
    for f in result["findings"]:
        lines.append(f"\n{ICON[f['severity']]} **{f['title']}**\n   {f['why']}\n   ➜ {f['fix']}")
    if result.get("errors"):
        lines.append(_t("\nNon letti dal firewall: ", "\nNot read from the firewall: ") + ", ".join(result["errors"]))
        for reason in dict.fromkeys(result["errors"].values()):
            lines.append(_t(f"   motivo: {reason}", f"   reason: {reason}"))
    return "\n".join(lines)
