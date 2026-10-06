# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""What Aurora can do on this installation, and what is missing for the rest.

One table: each feature names what it needs (models of config/models.json with all their files, paths of settings,
a switch, a program) and how to get it. `check` is asked before a feature is used, so that a missing model or
a switched-off setting becomes a clear answer ("to cut out the subject the SAM 2.1 model is needed: ...") and never
a crash in the middle of a job. The installer, the doctor script and the Status page show the same table.
Required features (reasoner, search) make the health red; optional ones only say what to install.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import sys_config

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "sys" / "core" / "config" / "models.json"
FETCH = ".venv/bin/python sys/core/script/sys_models_fetch.py --models {m} --yes"

# name: (required, {it, en} label, models (all files), setting paths that must exist, switch setting, programs)
FEATURES = {
    "reasoner": (True, {"it": "Ragionatore (chat, risposte)", "en": "Reasoner (chat, answers)"},
                 [], ["AURORA_LLM_MODEL"], None, []),
    "search": (True, {"it": "Ricerca nel vault (encoder e re-ranker)", "en": "Vault search (encoder and re-ranker)"},
               ["embedder", "reranker"], [], None, []),
    "vision": (False, {"it": "Visione (descrivere foto e video)", "en": "Vision (describing photos and videos)"},
               [], ["AURORA_LLM_MMPROJ"], None, []),
    "speech": (False, {"it": "Voce (dettatura, parlato dei video)", "en": "Speech (dictation, speech in videos)"},
               ["stt"], [], None, ["ffmpeg"]),
    "video_watch": (False, {"it": "Guardare i video allegati", "en": "Watching attached videos"},
                    [], [], None, ["ffmpeg", "ffprobe"]),
    "dreams": (False, {"it": "Sogni dipinti (SDXL-Lightning)", "en": "Painted dreams (SDXL-Lightning)"},
               ["image_base", "image_lora"], [], "AURORA_IMAGE_ENABLED", []),
    "edit_ai": (False, {"it": "Modifiche creative delle foto (FLUX.2 klein)", "en": "Creative photo edits (FLUX.2 klein)"},
                ["edit"], [], None, []),
    "upscale": (False, {"it": "Ingrandimento IA (Swin2SR)", "en": "AI enlargement (Swin2SR)"}, ["upscale"], [], None, []),
    "cutout": (False, {"it": "Scontorno (SAM 2.1)", "en": "Background removal (SAM 2.1)"}, ["segment"], [], None, []),
    "pdf_preview": (False, {"it": "Anteprima dei PDF", "en": "PDF preview"}, [], [], None, ["pdftoppm", "pdfinfo"]),
    "video_make": (False, {"it": "Creare video (Wan 2.2)", "en": "Making videos (Wan 2.2)"},
                   ["video"], [], None, ["ffmpeg"]),
    "voice_out": (False, {"it": "Voce di Aurora sui dispositivi senza voce (Piper)", "en": "Aurora's voice on devices without one (Piper)"},
                  ["tts"], ["AURORA_TTS_BIN"], "AURORA_TTS", []),
}
# what the installer offers, one question each: the models of a group and the features they open
GROUPS = {
    "dreams": {"models": ["image_base", "image_lora"], "features": ["dreams"], "default": True,
               "label": {"it": "Sogni dipinti", "en": "Painted dreams"}},
    "speech": {"models": ["stt"], "features": ["speech"], "default": True,
               "label": {"it": "Voce: dettatura e parlato dei video", "en": "Speech: dictation and speech in videos"}},
    "photo_tools": {"models": ["upscale", "segment"], "features": ["upscale", "cutout"], "default": True,
                    "label": {"it": "Foto: ingrandimento IA e scontorno (anche su CPU)",
                              "en": "Photos: AI enlargement and background removal (CPU too)"}},
    "photo_ai": {"models": ["edit"], "features": ["edit_ai"], "default": True,
                 "label": {"it": "Foto: modifiche creative a parole (FLUX.2 klein)",
                           "en": "Photos: creative edits in words (FLUX.2 klein)"}},
    "voice": {"models": ["tts"], "features": ["voice_out"], "default": True,
              "label": {"it": "Voce di Aurora (lettura ad alta voce, sulla CPU)", "en": "Aurora's voice (reading aloud, on the CPU)"}},
    "video": {"models": ["video"], "features": ["video_make"], "default": False,
              "label": {"it": "Creare video (~19 minuti per 5 secondi)", "en": "Making videos (~19 minutes for 5 seconds)"}},
}
# measured needs: VRAM on one GPU (GB, peak + margin), RAM of the machine (GB), where it was measured
HARDWARE = {"dreams": (7, 0, "M27: 6.21 GB"), "edit_ai": (10, 0, "M55: 9.23 GB"),
            "video_make": (14, 48, "M57: 13.88 GB, process 42 GB of RAM")}


def fits(profile: dict, group: str) -> tuple[bool, str]:
    """Whether this machine (sys_profile.py --json) can run a group, and why not."""
    vram = max((g.get("vram_gb", 0) for g in profile.get("gpus", [])), default=0)
    ram = profile.get("ram_gb", 0)
    for f in GROUPS[group]["features"]:
        need_vram, need_ram, why = HARDWARE.get(f, (0, 0, ""))
        if vram < need_vram:
            return False, f"GPU {vram:.0f} GB < {need_vram} GB ({why})"
        if ram < need_ram:
            return False, f"RAM {ram:.0f} GB < {need_ram} GB ({why})"
    return True, ""


def group_size_gb(group: str) -> float:
    man = manifest()
    return round(sum(man[m]["size_gb"] for m in GROUPS[group]["models"]), 2)


LLM_FILES = {"AURORA_LLM_MODEL": "llm", "AURORA_LLM_MMPROJ": "llm"}   # where a missing path comes from
SCRIPTS = {"tts": "bash sys/core/script/sys_tts_install.sh", "AURORA_TTS_BIN": "bash sys/core/script/sys_tts_install.sh"}


class Missing(RuntimeError):
    """A feature asked for and not available; the message says what to do."""

    def __init__(self, feature: str, text: str):
        super().__init__(text)
        self.feature = feature


def manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))["models"]


def _model_missing(cfg: sys_config.Config, name: str, m: dict) -> list[str]:
    """Files of manifest model `name` not on disk. A setting moved elsewhere by the owner is trusted if it exists."""
    moved = [k for k, default in m.get("settings", {}).items() if str(cfg.values.get(k, default)) != default]
    if moved:
        return [str(cfg.path(k)) for k in moved if not cfg.path(k).exists()]
    base = ROOT / m["dir"]
    return [f"{m['dir']}/{f}" for f in m["files"] if not (base / f).is_file() or (base / f).stat().st_size == 0]


def check(cfg: sys_config.Config, name: str) -> dict:
    """{"ok", "required", "label", "missing": [what], "fix": [commands or settings]}."""
    required, label, models, paths, switch, programs = FEATURES[name]
    man, missing, fix = manifest(), [], []
    for mname in models:
        lost = _model_missing(cfg, mname, man[mname]) if mname in man else ["not in models.json"]
        if lost:
            missing.append(f"{mname} ({len(lost)} file)")
            fix.append(SCRIPTS.get(mname) or FETCH.format(m=mname))
    for key in paths:
        if not cfg.path(key).is_file():
            missing.append(f"{key} = {cfg[key]}")
            fix.append(SCRIPTS.get(key) or FETCH.format(m=LLM_FILES.get(key, "llm")))
    if name == "vision" and missing:                 # vision assigned to a cloud model needs no local projector
        from . import mdl_router, sys_ethics
        a = mdl_router.assignments(cfg).get("vision", {})
        if a.get("provider", "local") != "local" and sys_ethics.exempt(cfg):
            missing, fix = [], []
    for p in programs:
        if not shutil.which(p):
            missing.append(p)
            fix.append(f"sudo apt install {'ffmpeg' if p.startswith('ff') else 'poppler-utils' if p.startswith('pdf') else p}")
    if switch and not cfg[switch]:
        missing.append(f"{switch} = off")
        fix.append(f"{switch}=1 (Impostazioni / Settings)")
    return {"ok": not missing, "required": required, "label": label, "missing": missing, "fix": sorted(set(fix))}


def report(cfg: sys_config.Config | None = None) -> dict:
    cfg = cfg or sys_config.get()
    return {name: check(cfg, name) for name in FEATURES}


def config_problems(cfg: sys_config.Config) -> list[str]:
    """Settings that contradict each other: a step given to a provider without its key, a switch on without its
    model. Each one would fail only when used; said here, at once."""
    from . import mdl_router
    out = []
    for role, a in mdl_router.assignments(cfg).items():
        p = mdl_router.PROVIDERS.get(a["provider"], {})
        if p.get("kind") not in ("local", "claude_code", None) and not cfg.values.get(p.get("key", "")):
            out.append(f"{role} → {a['provider']}: {p.get('key')} vuota (ricade sul locale)")
        if p.get("kind") == "openai" and not a.get("model"):
            out.append(f"{role} → {a['provider']}: nessun modello scelto (ricade sul locale)")
    for name, (_, _, _, _, switch, _) in FEATURES.items():
        if switch and cfg[switch]:
            c = check(cfg, name)
            if not c["ok"]:
                out.append(f"{switch} acceso ma {', '.join(c['missing'])} manca")
    return out


def ok(cfg: sys_config.Config, name: str) -> bool:
    return check(cfg, name)["ok"]


def need(cfg: sys_config.Config, name: str, lang: str = "it") -> None:
    """Raise Missing with a sentence for the owner when `name` is not available."""
    c = check(cfg, name)
    if c["ok"]:
        return
    lang = "it" if str(lang).lower().startswith("it") else "en"
    what, how = ", ".join(c["missing"]), " oppure ".join(c["fix"]) if lang == "it" else " or ".join(c["fix"])
    raise Missing(name, f"{c['label'][lang]}: non disponibile su questa installazione (manca {what}). Per attivarla: {how}"
                  if lang == "it" else
                  f"{c['label'][lang]}: not available on this installation ({what} missing). To enable it: {how}")
