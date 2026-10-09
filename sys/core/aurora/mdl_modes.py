# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""How Aurora is set up as a whole (owner, 2026-10-08: «massima libertà di configurazione, con indicazioni su dove
possono essere i rischi… basta che l'utente lo sappia»): four modes, and every aspect checked in each.

  local          everything on this machine
  mixed          the owner's own choice, step by step (the Models page's rows)
  cloud_private  every step that reasons, the service calls and the media to one cloud provider, masked; what holds
                 private data (health, the firewall) stays on a local model — or is off where there is none
  cloud_full     also the private data, masked, where no local reasoner runs: the owner's consent signed from a shell
                 (sys_cloud_consent), never from the web
The search over the vault has no cloud version: it stays here in every mode (on a CPU, M151). Aurora's voice goes to
the cloud in both cloud modes (its text masked, spoken by kind: mdl_media); dictation only in «all cloud» — the
owner's own voice cannot be masked (owner, 2026-10-09). Every cloud mode needs the level B exemption (rule 9), which is
signed from a shell too.
"""
from __future__ import annotations

import subprocess

from . import mdl_media, mdl_router, sys_cloud_consent, sys_config, sys_ethics, sys_features

MODES = ("local", "mixed", "cloud_private", "cloud_full")
EXEMPT_COMMAND = "sudo .venv/bin/python sys/core/script/sys_ethics_sign.py exempt"
SERVICES = ["aurora-api", "aurora-rem", "aurora-harvester"]       # they hold the reasoner they started with


class ModeError(ValueError):
    """A mode that cannot be applied now: why, and what the owner does about it (a setting, a shell command)."""

    def __init__(self, text: str, need: str, command: str = ""):
        super().__init__(text)
        self.need, self.command = need, command


def local_reasoner(cfg: sys_config.Config) -> bool:
    """A local reasoner on this machine: the backend is local and its model is on disk."""
    return not mdl_router.cloud_only(cfg) and sys_features.check(cfg, "reasoner")["ok"]


def can_have_local(cfg: sys_config.Config) -> bool:
    """The local reasoner could be switched on: its model and llama.cpp are here (a GPU machine)."""
    return cfg.path("AURORA_LLM_MODEL").is_file() and (cfg.path("AURORA_LLAMACPP_DIR") / "bin" / "llama-server").exists()


def current(cfg: sys_config.Config) -> str:
    """The mode the roles describe now. On a machine reasoning in the cloud, «local» in a row is the cloud default."""
    roles, media = mdl_router.assignments(cfg), mdl_media.assignments(cfg)
    default = str(cfg["AURORA_CLOUD_PROVIDER"]) if mdl_router.cloud_only(cfg) else "local"
    used = {default if a["provider"] == "local" else a["provider"] for r, a in roles.items() if r != "vision"}
    vision = default if roles["vision"]["provider"] == "local" else roles["vision"]["provider"]
    only_cli = len(used) == 1 and mdl_router.PROVIDERS.get(next(iter(used)), {}).get("kind") == "claude_code"
    if not (only_cli and vision == default):           # Claude Code sees no pictures: vision local is part of its mode
        used.add(vision)
    if used == {"local"}:
        return "local" if all(a["provider"] == "local" for a in media.values()) else "mixed"
    if len(used) == 1:
        return "cloud_full" if _consent(cfg) else "cloud_private"
    return "mixed"


def _consent(cfg) -> bool:
    return sys_ethics.exempt(cfg) and sys_cloud_consent.signed(cfg)


def _row(id_: str, it: str, en: str, now: str, **modes) -> dict:
    return {"id": id_, "it": it, "en": en, "now": now, "modes": modes}


def _s(state: str, it: str = "", en: str = "") -> dict:
    """ok ✅ · stay 🔒 (stays here by design) · warn ⚠️ (a risk the owner should know) · no ⛔ (not possible here)."""
    return {"state": state, "it": it, "en": en}


def check(cfg: sys_config.Config) -> dict:
    """The page's table: each aspect in each mode, what it is now, and what each cloud mode still needs."""
    cfg = now(cfg)
    local = local_reasoner(cfg)
    exempt, consent = sys_ethics.exempt(cfg), _consent(cfg)
    provider = str(cfg["AURORA_CLOUD_PROVIDER"])
    kind = mdl_router.PROVIDERS.get(provider, {}).get("kind", "")
    roles, media = mdl_router.assignments(cfg), mdl_media.assignments(cfg)
    no_local = _s("no", "nessun ragionatore locale su questa macchina", "no local reasoner on this machine")
    reason_now = sorted({a["provider"] for a in roles.values()})
    can = mdl_media.CAN.get(provider, {})
    rows = [
        _row("reasoning", "Ragionamento (le 12 fasi: risposte, agente, ciclo autonomo, forgia)",
             "Reasoning (the 12 steps: answers, agent, autonomic cycle, forge)", ", ".join(reason_now),
             local=_s("ok") if local else no_local, cloud_private=_s("ok", "mascherato", "masked"),
             cloud_full=_s("ok", "mascherato", "masked")),
        _row("service", "Chiamate di servizio (titoli, classificazione, fonti, bozze)",
             "Service calls (titles, classification, sources, drafts)", roles["service"]["provider"],
             local=_s("ok") if local else no_local, cloud_private=_s("ok", "mascherato", "masked"),
             cloud_full=_s("ok", "mascherato", "masked")),
        _row("vision", "Visione (foto e fotogrammi dei video)", "Vision (photos and video frames)", roles["vision"]["provider"],
             local=_s("ok") if local else no_local,
             cloud_private=(_s("no", "Claude Code non vede le immagini: resta locale", "Claude Code sees no pictures: stays local")
                            if kind == "claude_code" else _s("warn", "le foto non si possono mascherare", "photos cannot be masked")),
             cloud_full=(_s("no", "Claude Code non vede le immagini", "Claude Code sees no pictures") if kind == "claude_code"
                         else _s("warn", "le foto non si possono mascherare", "photos cannot be masked"))),
        _row("media", "Creare immagini, modifiche, video", "Making pictures, edits, videos",
             ", ".join(f"{t}: {a['provider']}" for t, a in media.items() if t in ("image", "edit", "video")),
             local=_s("ok" if sys_features.check(cfg, "dreams")["ok"] else "warn", "" if sys_features.check(cfg, "dreams")["ok"]
                      else "modelli non scaricati (o niente GPU)", "" if sys_features.check(cfg, "dreams")["ok"]
                      else "models not downloaded (or no GPU)"),
             cloud_private=_media_state(provider, {t: m for t, m in can.items() if t in ("image", "edit", "video")}),
             cloud_full=_media_state(provider, {t: m for t, m in can.items() if t in ("image", "edit", "video")})),
        _row("search", "Ricerca nel vault (encoder e riordinatore)", "Vault search (encoder and re-ranker)",
             str(cfg["AURORA_EMBEDDER_DEVICE"]), local=_s("ok"),
             cloud_private=_s("stay", "resta qui: in cloud andrebbe tutto il vault", "stays here: the whole vault would leave"),
             cloud_full=_s("stay", "resta qui (nessuna versione cloud); su CPU bastano 12 GB di RAM",
                           "stays here (no cloud version); on a CPU 12 GB of RAM are enough")),
        _row("voice", "Voce di Aurora", "Aurora's voice", media["voice"]["provider"],
             local=_s("ok") if sys_features.check(cfg, "voice_out")["ok"] else _s("warn", "Piper non installata: spenta",
                                                                                   "Piper not installed: off"),
             cloud_private=(_s("ok", "testo mascherato, i dati sensibili detti per tipo", "text masked, private data said by kind")
                            if "voice" in can else _s("no", f"{provider} non ha una voce", f"{provider} has no voice")),
             cloud_full=(_s("ok", "testo mascherato", "text masked") if "voice" in can
                         else _s("no", f"{provider} non ha una voce", f"{provider} has no voice"))),
        _row("speech", "Dettatura e parlato dei video", "Dictation and the speech of videos", media["speech"]["provider"],
             local=_s("ok") if sys_features.check(cfg, "speech")["ok"] else _s("warn", "Whisper non installato: spenta",
                                                                                 "Whisper not installed: off"),
             cloud_private=_s("stay", "resta qui: la tua voce non si può mascherare", "stays here: your voice cannot be masked"),
             cloud_full=(_s("warn", "la tua voce esce, non mascherata", "your voice leaves, not masked") if "speech" in can
                         else _s("no", f"{provider} non trascrive", f"{provider} does not transcribe"))),
        _row("private", "Dati privati (salute, configurazione del firewall)", "Private data (health, the firewall's configuration)",
             "local" if local else ("cloud" if consent else "off"),
             local=_s("ok") if local else _s("warn", "nessun modello locale: le funzioni private sono spente",
                                             "no local model: the private features are off"),
             cloud_private=(_s("stay", "restano sul modello locale", "stay on the local model") if local else
                            _s("warn", "senza modello locale sono spente (valori delle analisi a mano)",
                               "without a local model they are off (exam values by hand)")),
             cloud_full=(_s("stay", "restano sul ragionatore locale finché è acceso", "stay on the local reasoner while it runs")
                         if local else _s("warn", "escono, mascherate: consenso da shell",
                                          "they leave, masked: consent from a shell"))),
    ]
    needs = []
    if not exempt:
        needs.append({"need": "exempt", "it": "Ogni modalità cloud richiede l'esenzione dal livello B (regola 9).",
                      "en": "Every cloud mode needs the exemption from level B (rule 9).", "command": EXEMPT_COMMAND})
    if not mdl_router.configured(provider, cfg):
        needs.append({"need": "key", "it": f"{provider}: manca la chiave o l'indirizzo (scheda del plugin ☁️ cloud).",
                      "en": f"{provider}: its key or address is missing (the ☁️ cloud plugin's card).", "command": ""})
    if not consent:
        needs.append({"need": "consent", "it": "«Tutto cloud» richiede il tuo consenso firmato da shell.",
                      "en": "«Tutto cloud» needs your consent, signed from a shell.", "command": sys_cloud_consent.COMMAND})
    return {"mode": current(cfg), "local_reasoner": local, "can_have_local": can_have_local(cfg),
            "backend": "cloud" if mdl_router.cloud_only(cfg) else "local", "exempt": exempt, "consent": consent,
            "provider": provider, "model": str(cfg["AURORA_CLOUD_MODEL"] or ""), "aspects": rows, "needs": needs}


def _media_state(provider: str, can: dict) -> dict:
    if not can:
        return _s("no", f"{provider} non crea immagini né video: restano locali", f"{provider} makes no pictures or videos: they stay local")
    tasks = ", ".join(can)
    full = set(can) == set(mdl_media.TASKS)
    return _s("ok" if full else "warn", f"{provider}: {tasks}" + ("" if full else "; il resto locale"),
              f"{provider}: {tasks}" + ("" if full else "; the rest local"))


def apply(cfg: sys_config.Config, mode: str, provider: str = "", model: str = "") -> dict:
    """Every role (and what the provider can of the media) to the mode; «mixed» changes nothing (the rows do)."""
    if mode not in MODES:
        raise ValueError(f"mode: one of {MODES}")
    cfg = now(cfg)
    if mode == "mixed":
        return {"mode": current(cfg), "restart": []}
    if mode == "local":
        if not local_reasoner(cfg):
            raise ModeError("questa macchina non ha un ragionatore locale acceso: prima accendilo (o resta in cloud)",
                            "local_model")
        mdl_router.set_assignments(cfg, {r: {"provider": "local", "model": ""} for r in mdl_router.ROLES})
        mdl_media.set_assignments(cfg, {t: {"provider": "local", "model": ""} for t in mdl_media.TASKS})
        sys_cloud_consent.revoke(cfg)
        return {"mode": current(cfg), "restart": []}
    provider = provider or str(cfg["AURORA_CLOUD_PROVIDER"])
    model = model or (str(cfg["AURORA_CLOUD_MODEL"] or "") if provider == cfg["AURORA_CLOUD_PROVIDER"] else "")
    spec = mdl_router.PROVIDERS.get(provider)
    if spec is None or spec["kind"] == "local":
        raise ValueError(f"provider: one of {', '.join(p for p in mdl_router.PROVIDERS if p != 'local')}")
    if not sys_ethics.exempt(cfg):
        raise ModeError("ogni modalità cloud richiede l'esenzione dal livello B, firmata da shell", "exempt", EXEMPT_COMMAND)
    if not mdl_router.configured(provider, cfg):
        raise ModeError(f"{provider}: manca la chiave o l'indirizzo, nella scheda del plugin ☁️ cloud", "key")
    if spec["kind"] == "openai" and not model:
        raise ModeError(f"{provider}: scegli il modello (📋 elenco)", "model")
    if mode == "cloud_full" and not sys_cloud_consent.signed(cfg):
        raise ModeError("«Tutto cloud» manda fuori anche i dati privati, mascherati: serve il tuo consenso firmato da shell",
                        "consent", sys_cloud_consent.COMMAND)
    if mode == "cloud_private":
        sys_cloud_consent.revoke(cfg)
    roles = {r: {"provider": provider, "model": model} for r in mdl_router.ROLES}
    if spec["kind"] == "claude_code":
        roles["vision"] = {"provider": "local", "model": ""}       # the CLI sees no pictures
    mdl_router.set_assignments(cfg, roles)
    can = dict(mdl_media.CAN.get(provider, {}))
    if mode == "cloud_private":
        can.pop("speech", None)                       # the owner's voice cannot be masked: dictation stays here
    mdl_media.set_assignments(cfg, {t: ({"provider": provider, "model": ""} if t in can else {"provider": "local", "model": ""})
                                    for t in mdl_media.TASKS})
    changed = (provider, model) != (str(cfg["AURORA_CLOUD_PROVIDER"]), str(cfg["AURORA_CLOUD_MODEL"] or ""))
    sys_config.write_env(_env(cfg), {"AURORA_CLOUD_PROVIDER": provider, "AURORA_CLOUD_MODEL": model})
    # the cloud default is read when the services start: only a machine reasoning in the cloud needs them again
    return {"mode": mode, "restart": SERVICES if changed and mdl_router.cloud_only(cfg) else []}


def _env(cfg):
    return (getattr(cfg, "base", None) or cfg).env_file


def now(cfg: sys_config.Config) -> sys_config.Config:
    """The settings as the .env holds them now (a service keeps the ones it started with)."""
    return sys_config.load(_env(cfg), check_root=False)


def _service(verb: str, run=subprocess.run) -> tuple[int, str]:
    """aurora-llm started or stopped (50-aurora.rules lets the service user do it, no sudo)."""
    r = run(["systemctl", verb, "aurora-llm"], capture_output=True, text=True, timeout=120)
    return r.returncode, (r.stderr or r.stdout).strip()


def reasoner(cfg: sys_config.Config, on: bool, run=subprocess.run) -> dict:
    """The local reasoner switched off (the GPU free, Aurora reasons with the cloud default) or on again."""
    cfg = now(cfg)
    if on:
        if not can_have_local(cfg):
            raise ModeError("il modello locale o llama.cpp non sono su questa macchina: si installano con ./install.sh",
                            "local_model", "./install.sh")
        from . import sys_health
        job = sys_health.gpu_job(cfg)
        if job:                                        # rule 6: one GPU, one job
            raise ModeError(f"la GPU sta lavorando ({job}): riprova alla fine", "gpu")
        sys_config.write_env(_env(cfg), {"AURORA_LLM_BACKEND": "local"})
        code, said = _service("start", run)
    else:
        if not sys_ethics.exempt(cfg):
            raise ModeError("senza ragionatore locale Aurora ragiona in cloud: serve l'esenzione dal livello B", "exempt",
                            EXEMPT_COMMAND)
        why = mdl_router.CloudBase(cfg).problem()
        if why:
            raise ModeError(f"prima scegli il provider cloud predefinito ({why})", "key")
        sys_config.write_env(_env(cfg), {"AURORA_LLM_BACKEND": "cloud"})
        code, said = _service("stop", run)
    if code != 0:
        sys_config.write_env(_env(cfg), {"AURORA_LLM_BACKEND": "cloud" if on else "local"})     # as it was
        raise ModeError(f"aurora-llm: {said[-200:]}", "service")
    return {"backend": "local" if on else "cloud", "restart": SERVICES}
