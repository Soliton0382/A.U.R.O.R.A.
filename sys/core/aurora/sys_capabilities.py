# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""What this installation can do now, read live (owner, 2026-10-06: "the features list is incomplete: make it dynamic").

sys_features says which models and programs are on disk; this adds what changes while Aurora runs: every plugin (on,
off, keys missing, error), the connections (cloud providers with a key, the firewall's API, notifications, backup) and
the abilities built on top (the answers' shadow, her own voice, the network map, the synapses). Each line is read from
the module that owns it; one that fails says so instead of breaking the Status page.
"""
from __future__ import annotations

import shutil

from . import sys_config
from .sys_lang import say as _t   # each sentence in the reader's language (C526)


def _line(name: str, ok: bool, it: str, en: str, detail: str = "", fix: str = "") -> dict:
    return {"name": name, "ok": bool(ok), "label": {"it": it, "en": en}, "detail": detail, "fix": fix}


def _safe(name: str, it: str, en: str, fn) -> dict:
    try:
        return fn()
    except Exception as e:  # noqa: BLE001 — one check that fails is a line, never a broken page
        return _line(name, False, it, en, f"{type(e).__name__}: {str(e)[:120]}")


def plugins(host) -> list[dict]:
    out = []
    for p in host.plugins(with_tools=False):
        detail = _t(("" if p.available else "spento" if not p.enabled else
                  f"mancano: {', '.join(p.missing)}" if p.missing else p.error[:120]), ("" if p.available else "off" if not p.enabled else
                  f"missing: {', '.join(p.missing)}" if p.missing else p.error[:120]))
        out.append(_line(f"plugin:{p.name}", p.available, p.name, p.name, detail,
                         "" if p.available or not p.enabled else "🧩 Plugin → " + p.name))
    return out


def connections(cfg: sys_config.Config) -> list[dict]:
    from . import mdl_router
    out = []
    for name, spec in mdl_router.PROVIDERS.items():
        if spec.get("key"):
            ready = mdl_router.configured(name, cfg)
            out.append(_line(f"cloud:{name}", ready, spec["label"], spec["label"],
                             _t("pronto" if ready else "nessuna chiave o indirizzo", "ready" if ready else "no key or address"), f"{spec.get('base_key') or spec['key']} (🧠 Modelli)"))
    found = shutil.which(str(cfg["AURORA_CLAUDE_CODE_BIN"]))    # where the calls look (C497: not on the services' PATH)
    out.append(_line("cloud:claude_code", bool(found), "Claude Code (abbonamento)", "Claude Code (subscription)",
                     _t("programma trovato" if found else "programma non trovato", "program found" if found else "program not found"), "AURORA_CLAUDE_CODE_BIN"))

    def firewall():
        from . import sec_firewalls
        on = sec_firewalls.receivers(cfg)
        return _line("firewall", bool(on), "API del firewall", "Firewall API",
                     ", ".join(f"{x['name']} ({x['kind']})" for x in on) if on else _t("non configurata", "not configured"), "🛡️ Security → Firewall")

    def push():
        from . import sys_push
        n = sys_push.count(cfg)
        return _line("push", n > 0, "Notifiche sui dispositivi", "Notifications on devices", _t(f"{n} dispositivi iscritti", f"{n} devices subscribed"),
                     _t("🔔 nella WebUI di ogni dispositivo", "🔔 in each device's WebUI"))

    def backup():
        from . import sys_backup
        b = sys_backup.status(cfg)
        last = (b.get("last") or {}).get("finished") or (b.get("last") or {}).get("at")
        return _line("backup", b["configured"] and not b["problem"], "Backup cifrato", "Encrypted backup",
                     b["problem"] or _t(f"{len(b['snapshots'])} copie" + (f", ultima {str(last)[:16]}" if last else ""), f"{len(b['snapshots'])} copies" + (f", the last {str(last)[:16]}" if last else "")))
    out += [_safe("firewall", "API del firewall", "Firewall API", firewall), _safe("push", "Notifiche", "Notifications", push),
            _safe("backup", "Backup cifrato", "Encrypted backup", backup)]
    return out


def abilities(cfg: sys_config.Config) -> list[dict]:
    def shadow():
        from . import kno_shadow
        s = kno_shadow.stats(cfg)
        return _line("shadow", bool(cfg["AURORA_SHADOW"]), "Ombra delle risposte", "Answer shadow",
                     _t(f"{s['answers']} risposte ({s['seed']} del seme), servite {s['served']} volte", f"{s['answers']} answers ({s['seed']} of the seed), served {s['served']} times"))

    def voice():
        from . import mdl_tts
        a = mdl_tts.available(cfg)
        return _line("voice", a["enabled"] and bool(a["languages"]), "Voce di Aurora (Piper)", "Aurora's voice (Piper)",
                     ", ".join(a["languages"]) or _t("non installata", "not installed"), "bash sys/core/script/sys_tts_install.sh")

    def netmap():
        import time
        from . import sec_netmap
        s = sec_netmap.summary(sec_netmap.load(cfg))
        return _line("netmap", bool(s.get("at")), "Mappa della rete", "Network map",
                     f"{s['devices']} " + _t("dispositivi", "devices") + f", {time.strftime('%d/%m %H:%M', time.localtime(s['at']))}" if s.get("at")
                     else _t("mai letta", "never read"), _t("🛡️ Sicurezza → Difesa e rete → Guarda la rete", "🛡️ Security → Defence and network → Look at the network"))

    def synapses():
        from . import kno_synapse
        s = kno_synapse.stats(cfg)
        return _line("synapses", s["links"] > 0, "Sinapsi", "Synapses", f"{s['links']} collegamenti, {s['concepts']} concetti")

    def study():
        n = int(cfg["AURORA_STUDY_PER_NIGHT"])
        return _line("study", n > 0, "Studio notturno", "Night study", _t(f"fino a {n} domande a notte" if n else "spento", f"up to {n} questions a night" if n else "off"))

    def avatar():                                        # 🪪 the people's cards (sys_people, api/people)
        from . import sys_features
        f = sys_features.report(cfg)
        ways = [w for k, w in _t((("edit_ai", "dalla foto"), ("dreams", "dalle parole")), (("edit_ai", "from the photo"), ("dreams", "from the words"))) if f.get(k, {}).get("ok")]
        return _line("avatar", bool(ways), "Avatar delle schede", "The cards' avatars",
                     _t(", ".join(ways) + " (modelli locali)" if ways else "servono i modelli delle immagini", ", ".join(ways) + " (local models)" if ways else "the picture models are needed"),
                     ".venv/bin/python sys/core/script/sys_models_fetch.py --models photo_ai --yes")

    def invites():                                       # 👥 the calendar's invitations by e-mail (cal_share)
        ok = all(str(cfg.values.get(k) or "") for k in ("AURORA_EMAIL_SMTP_HOST", "AURORA_EMAIL_USER", "AURORA_EMAIL_PASSWORD"))
        return _line("invites", ok, "Inviti del calendario per email", "Calendar invitations by e-mail",
                     _t("dalla casella del plugin ✉️" if ok else "il plugin ✉️ email non è configurato", "from the ✉️ plugin's mailbox" if ok else "the ✉️ email plugin is not configured"),
                     _t("🔌 Plugin → ✉️ email → ⚙️ (server, indirizzo, password per le app)", "🔌 Plugins → ✉️ email → ⚙️ (server, address, app password)"))
    return [_safe(n, it, en, f) for n, it, en, f in (
        ("shadow", "Ombra delle risposte", "Answer shadow", shadow), ("voice", "Voce di Aurora", "Aurora's voice", voice),
        ("netmap", "Mappa della rete", "Network map", netmap), ("synapses", "Sinapsi", "Synapses", synapses),
        ("study", "Studio notturno", "Night study", study), ("avatar", "Avatar delle schede", "The cards' avatars", avatar),
        ("invites", "Inviti del calendario per email", "Calendar invitations by e-mail", invites))]


def report(cfg: sys_config.Config, host) -> dict:
    return {"plugins": plugins(host), "connections": connections(cfg), "abilities": abilities(cfg)}
