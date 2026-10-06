# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The doctors' cards (owner, 2026-10-06: "every time I go mad looking for the photo of the hours on WhatsApp"): for each
doctor (the family doctor, a paediatrician, a dentist...) the hours of the week, phone, address, how to book and notes.

Sealed with the user's own key like the rest of Health (sys_seal), one file per user; read by the local model only (the
health plugin is private) to answer "a che ora riceve oggi il medico?".
"""
from __future__ import annotations

import json
import re
import secrets
from datetime import datetime

from . import sys_config, sys_seal

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat")
NAMES_IT = {"mon": "lunedì", "tue": "martedì", "wed": "mercoledì", "thu": "giovedì", "fri": "venerdì", "sat": "sabato"}
FIELDS = ("role", "name", "phone", "address", "booking", "notes")
MAX = 12


def _file(cfg: sys_config.Config):
    d = cfg.path("AURORA_HEALTH_DIR")
    d.mkdir(parents=True, exist_ok=True)
    return d / "doctors.sealed"


def load(cfg: sys_config.Config) -> list[dict]:
    f = _file(cfg)
    return json.loads(sys_seal.read(cfg, f, cfg.user)) if f.exists() else []


def clean(card: dict) -> dict:
    """A card as the page sends it, kept to its fields and to sane lengths."""
    out = {k: str(card.get(k) or "").strip()[:2000 if k == "notes" else 200] for k in FIELDS}
    hours = card.get("hours") or {}
    out["hours"] = {d: {p: str((hours.get(d) or {}).get(p) or "").strip()[:60] for p in ("am", "pm")} for d in DAYS}
    out["id"] = re.sub(r"[^a-z0-9]", "", str(card.get("id") or "")) or secrets.token_hex(4)
    return out


def save(cfg: sys_config.Config, cards: list[dict]) -> list[dict]:
    cards = [clean(c) for c in cards[:MAX] if isinstance(c, dict)]
    sys_seal.write(cfg, _file(cfg), json.dumps(cards, ensure_ascii=False).encode(), cfg.user)
    return cards


def text(cards: list[dict], now: datetime | None = None) -> str:
    """The cards for the model: every field, the week's hours, and which day is today."""
    now = now or datetime.now()
    today = DAYS[now.weekday()] if now.weekday() < len(DAYS) else ""
    out = [f"Oggi è {NAMES_IT.get(today, 'domenica')} {now:%d/%m/%Y}, ore {now:%H:%M}."]
    for c in cards:
        head = " — ".join(x for x in (c.get("role"), c.get("name")) if x) or "Medico"
        lines = [f"## {head}"]
        lines += [f"{label}: {c[k]}" for k, label in (("phone", "Telefono"), ("address", "Indirizzo"),
                                                       ("booking", "Come prenotare")) if c.get(k)]
        week = [f"- {NAMES_IT[d]}: " + (", ".join(x for x in (c['hours'][d]['am'], c['hours'][d]['pm']) if x) or "chiuso")
                for d in DAYS]
        lines += ["Orari:"] + week
        if c.get("notes"):
            lines.append(f"Note: {c['notes']}")
        out.append("\n".join(lines))
    return "\n\n".join(out) if cards else "Nessun medico inserito: si aggiunge nella pagina ❤️ Salute → Medico."
