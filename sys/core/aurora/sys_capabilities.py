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
        detail = ("" if p.available else "spento" if not p.enabled else
                  f"mancano: {', '.join(p.missing)}" if p.missing else p.error[:120])
        out.append(_line(f"plugin:{p.name}", p.available, p.name, p.name, detail,
                         "" if p.available or not p.enabled else "🧩 Plugin → " + p.name))
    return out


def connections(cfg: sys_config.Config) -> list[dict]:
    from . import mdl_router
    out = []
    for name, spec in mdl_router.PROVIDERS.items():
        if spec.get("key"):
            out.append(_line(f"cloud:{name}", bool(cfg.values.get(spec["key"])), spec["label"], spec["label"],
                             "chiave presente" if cfg.values.get(spec["key"]) else "nessuna chiave", f"{spec['key']} (🧠 Modelli)"))
    out.append(_line("cloud:claude_code", bool(shutil.which("claude")), "Claude Code (abbonamento)", "Claude Code (subscription)",
                     "programma trovato" if shutil.which("claude") else "programma non trovato"))

    def firewall():
        from . import sec_fwapi
        return _line("firewall", sec_fwapi.configured(cfg), "API del firewall", "Firewall API",
                     cfg["AURORA_FIREWALL_API_KIND"] if sec_fwapi.configured(cfg) else "non configurata", "🧩 Plugin → security")

    def push():
        from . import sys_push
        n = sys_push.count(cfg)
        return _line("push", n > 0, "Notifiche sui dispositivi", "Notifications on devices", f"{n} dispositivi iscritti",
                     "🔔 nella WebUI di ogni dispositivo")

    def backup():
        from . import sys_backup
        b = sys_backup.status(cfg)
        last = (b.get("last") or {}).get("finished") or (b.get("last") or {}).get("at")
        return _line("backup", b["configured"] and not b["problem"], "Backup cifrato", "Encrypted backup",
                     b["problem"] or f"{len(b['snapshots'])} copie" + (f", ultima {str(last)[:16]}" if last else ""))
    out += [_safe("firewall", "API del firewall", "Firewall API", firewall), _safe("push", "Notifiche", "Notifications", push),
            _safe("backup", "Backup cifrato", "Encrypted backup", backup)]
    return out


def abilities(cfg: sys_config.Config) -> list[dict]:
    def shadow():
        from . import kno_shadow
        s = kno_shadow.stats(cfg)
        return _line("shadow", bool(cfg["AURORA_SHADOW"]), "Ombra delle risposte", "Answer shadow",
                     f"{s['answers']} risposte ({s['seed']} del seme), servite {s['served']} volte")

    def voice():
        from . import mdl_tts
        a = mdl_tts.available(cfg)
        return _line("voice", a["enabled"] and bool(a["languages"]), "Voce di Aurora (Piper)", "Aurora's voice (Piper)",
                     ", ".join(a["languages"]) or "non installata", "bash sys/core/script/sys_tts_install.sh")

    def netmap():
        import time
        from . import sec_netmap
        s = sec_netmap.summary(sec_netmap.load(cfg))
        return _line("netmap", bool(s.get("at")), "Mappa della rete", "Network map",
                     f"{s['devices']} dispositivi, {time.strftime('%d/%m %H:%M', time.localtime(s['at']))}" if s.get("at")
                     else "mai letta", "🛡️ Sicurezza → Difesa e rete → Guarda la rete")

    def synapses():
        from . import kno_synapse
        s = kno_synapse.stats(cfg)
        return _line("synapses", s["links"] > 0, "Sinapsi", "Synapses", f"{s['links']} collegamenti, {s['concepts']} concetti")

    def study():
        n = int(cfg["AURORA_STUDY_PER_NIGHT"])
        return _line("study", n > 0, "Studio notturno", "Night study", f"fino a {n} domande a notte" if n else "spento")
    return [_safe(n, it, en, f) for n, it, en, f in (
        ("shadow", "Ombra delle risposte", "Answer shadow", shadow), ("voice", "Voce di Aurora", "Aurora's voice", voice),
        ("netmap", "Mappa della rete", "Network map", netmap), ("synapses", "Sinapsi", "Synapses", synapses),
        ("study", "Studio notturno", "Night study", study))]


def report(cfg: sys_config.Config, host) -> dict:
    return {"plugins": plugins(host), "connections": connections(cfg), "abilities": abilities(cfg)}
