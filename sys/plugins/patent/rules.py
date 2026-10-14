# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The patent offices' rules of form, each number with its source (ROADMAP 100). Lengths in millimetres.

IT  D.M. 13 gennaio 2010, n. 33 (Regolamento di attuazione del Codice della proprietà industriale), art. 22 —
    in Aurora's vault (law_it, Normattiva): A4; text and drawings with margins of at least 2.5 cm on every side;
    line spacing 1½; capitals at least 0.21 cm; drawings numbered progressively, and every number and letter of the
    drawings recalled in the description (art. 22.3).
EP  EPC Implementing Regulations: Rule 46 (drawings: margins top 25, left 25, right 15, bottom 10; «Fig.»; sheets
    «1/n»; reference signs ≥ 3.2 mm), Rule 47(3) (abstract preferably ≤ 150 words), Rule 49 (text: A4; margins top
    20, left 25, right 20, bottom 20; line spacing 1½; capitals ≥ 2.1 mm; pages numbered), Rule 43 (claims in Arabic
    numerals).
US  37 CFR 1.52 (A4 or letter; margins top 20, left 25, right 20, bottom 20; 1½ or double spacing; capitals ≥ 2.1 mm;
    pages numbered), 1.72(b) (abstract ≤ 150 words, a separate sheet headed «Abstract»), 1.75(h) (claims begin on a
    separate sheet), 1.84 (drawings: margins top 25, left 25, right 15, bottom 10; «FIG.»; sheets «1/n»; reference
    characters ≥ 3.2 mm), 1.52(b)(6) (paragraphs may be numbered [0001]); 35 U.S.C. 111(b): a provisional needs a
    specification and drawings, claims not required.
"""
from __future__ import annotations

OFFICES = {
    "IT": {"name": "Ufficio Italiano Brevetti e Marchi", "page": "A4",
           "text_margins": {"top": 25, "left": 25, "right": 25, "bottom": 25},
           "drawing_margins": {"top": 25, "left": 25, "right": 25, "bottom": 25},
           "spacing": 1.5, "cap_mm": 2.1, "abstract_words": None, "fig": "Fig.", "paragraph_numbers": False,
           "claims_required": True, "signs_in_description": True,
           "source": "D.M. 13 gennaio 2010, n. 33, art. 22"},
    "EP": {"name": "European Patent Office", "page": "A4",
           "text_margins": {"top": 20, "left": 25, "right": 20, "bottom": 20},
           "drawing_margins": {"top": 25, "left": 25, "right": 15, "bottom": 10},
           "spacing": 1.5, "cap_mm": 2.1, "abstract_words": 150, "fig": "Fig.", "paragraph_numbers": False,
           "claims_required": True, "signs_in_description": True,
           "source": "EPC Rules 43, 46, 47(3), 49"},
    "US": {"name": "United States Patent and Trademark Office", "page": "letter",
           "text_margins": {"top": 20, "left": 25, "right": 20, "bottom": 20},
           "drawing_margins": {"top": 25, "left": 25, "right": 15, "bottom": 10},
           "spacing": 1.5, "cap_mm": 2.1, "abstract_words": 150, "fig": "FIG.", "paragraph_numbers": True,
           "claims_required": False, "signs_in_description": True,
           "source": "37 CFR 1.52, 1.72(b), 1.75(h), 1.84; 35 U.S.C. 111(b) (provisional)"},
}
PAGES = {"A4": (210.0, 297.0), "letter": (215.9, 279.4)}
SIGN_MM = 3.2                            # reference signs at least 3.2 mm high (EPC R. 46(2)(i), 37 CFR 1.84(p)(3))
# what a public filing must not carry: an AI notice printed or in the metadata (owner, 2026-10-14: «i documenti
# prodotti non devono avere ai act stampato sopra perché poi vanno in uffici pubblici»)
AI_MARKS = ("generated with artificial intelligence", "generato con intelligenza artificiale", "ai-generated",
            "contenuto generato", "content generated", "aurora", "synthetic content", "c2pa", "trainedalgorithmicmedia")


def office(code: str) -> dict:
    c = (code or "").upper()
    if c not in OFFICES:
        raise ValueError(f"office: one of {', '.join(OFFICES)}")
    return {"code": c, **OFFICES[c]}
