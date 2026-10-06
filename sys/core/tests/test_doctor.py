# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The doctors' cards (owner, 2026-10-06): sealed, cleaned, told to the model with today's day."""
from datetime import datetime

from aurora import hlt_doctor


def test_cards_are_sealed_cleaned_and_told_with_today(cfg):
    cards = hlt_doctor.save(cfg, [{"role": "Medico di base", "name": "Dott.ssa Rossi", "phone": "0123 456",
                                   "hours": {"mon": {"am": "9:00–12:00"}, "wed": {"pm": "16:00–19:00"}},
                                   "notes": "Ricette: lasciare la richiesta in segreteria", "evil": "x"}])
    assert "evil" not in cards[0] and cards[0]["id"] and cards[0]["hours"]["tue"] == {"am": "", "pm": ""}
    raw = hlt_doctor._file(cfg).read_bytes()
    assert b"Rossi" not in raw                                   # sealed, not readable on disk
    assert hlt_doctor.load(cfg)[0]["name"] == "Dott.ssa Rossi"
    text = hlt_doctor.text(hlt_doctor.load(cfg), datetime(2026, 10, 7, 10, 30))       # a Wednesday
    assert "Oggi è mercoledì 07/10/2026" in text and "- lunedì: 9:00–12:00" in text and "- martedì: chiuso" in text
    assert "- mercoledì: 16:00–19:00" in text and "Telefono: 0123 456" in text and "Note: Ricette" in text
    assert hlt_doctor.text([]).startswith("Nessun medico")
    assert "Oggi è domenica" in hlt_doctor.text(cards, datetime(2026, 10, 11, 9))
