# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Identifiers found in a page's text, each checked before it may carry a strong link (PLAN: «il controllo dei numeri»:
OCR misreads exactly the digits, and a misread account makes a false link). Every hit says where it is (start, end) and
whether it passed its check: an IBAN its mod-97, a US routing number its ABA checksum, a BIC its form, coordinates their
range. A value that fails stays, marked doubtful — never dropped, never a strong link."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Hit:
    kind: str          # iban, bic, aba, account, coords, amount, tail, tracking
    value: str         # normalized
    start: int
    end: int
    valid: bool        # its check passed (True when the kind has no check but its form is exact)


# ---- the checks ------------------------------------------------------------------------------------------------
IBAN_LENGTHS = {"AD": 24, "AE": 23, "AT": 20, "BE": 16, "BH": 22, "BS": 0, "CH": 21, "CY": 28, "CZ": 24, "DE": 22,
                "DK": 18, "ES": 24, "FI": 18, "FR": 27, "GB": 22, "GI": 23, "GR": 27, "HK": 0, "IE": 22, "IL": 23,
                "IT": 27, "LI": 21, "LU": 20, "MC": 27, "MT": 31, "NL": 18, "NO": 15, "PL": 28, "PT": 25, "SA": 24,
                "SE": 24, "SM": 27, "VG": 24}


def iban_ok(value: str) -> bool:
    s = value.replace(" ", "").upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", s):
        return False
    if IBAN_LENGTHS.get(s[:2], len(s)) not in (len(s), 0):
        return False
    n = "".join(str(int(c, 36)) for c in s[4:] + s[:4])
    return int(n) % 97 == 1


def aba_ok(value: str) -> bool:
    """A US bank routing number: 9 digits, weights 3-7-1, the sum a multiple of 10."""
    d = [int(c) for c in value if c.isdigit()]
    if len(d) != 9:
        return False
    return sum(w * x for w, x in zip([3, 7, 1] * 3, d)) % 10 == 0 and d[0] in (0, 1, 2, 3, 6, 7, 8)


def bic_ok(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?", value)) and value[4:6].isalpha()


def coords_ok(lat: float, lon: float) -> bool:
    return -90 <= lat <= 90 and -180 <= lon <= 180 and not (lat == 0 and lon == 0)


# ---- finding them in a text ---------------------------------------------------------------------------------------
RX = {
    "iban": re.compile(r"\b([A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?)\b"),
    "bic": re.compile(r"\b(?:SWIFT|BIC)(?:\s*(?:code|no\.?|#))?[:\s]+([A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)\b", re.I),
    "aba": re.compile(r"\b(?:ABA|routing)(?:\s*(?:no\.?|number|#))?[:\s]+(\d{9})\b", re.I),
    "account": re.compile(r"\b(?:acct|account)(?:\s*(?:no\.?|number|#))?[:\s]+([0-9][0-9\- ]{5,20}[0-9])\b", re.I),
    "tail": re.compile(r"\b(N\d{1,5}[A-Z]{0,2})\b"),                       # a US aircraft's registration
    "amount": re.compile(r"(?:(USD|EUR|GBP|CHF)\s?|([$€£]))\s?(\d{1,3}(?:[,.]\d{3})+(?:[.,]\d{2})?|\d+(?:[.,]\d{2})?)"),
    "coords": re.compile(r"(-?\d{1,2}\.\d{3,8})\s*[,;]\s*(-?\d{1,3}\.\d{3,8})"),
    "dms": re.compile(r"(\d{1,2})°\s*(\d{1,2})['′]\s*(\d{1,2}(?:\.\d+)?)?[\"″]?\s*([NS])[,\s]+(\d{1,3})°\s*(\d{1,2})['′]\s*"
                      r"(\d{1,2}(?:\.\d+)?)?[\"″]?\s*([EW])"),
}


def _dms(d, m, s, hemi) -> float:
    v = int(d) + int(m) / 60 + (float(s) if s else 0) / 3600
    return -v if hemi in "SW" else v


# B3 (measured on the archive, 12 Nov): a US registration is N, a digit 1–9, up to four more digits, up to two letters
# but never I or O, six characters at most; a short one (N1, N4G: notes, footnotes) only beside words of flying
TAIL_FORM = re.compile(r"N[1-9]\d{0,4}[A-HJ-NP-Z]{0,2}")
FLYING = re.compile(r"\b(aircraft|tail|registration|reg|n-number|plane|jet|gulfstream|boeing|cessna|learjet|falcon|"
                    r"helicopter|flights?|pilot|faa|hangar|airport|airplane|sikorsky|aviation)\b", re.I)


def find(text: str) -> list[Hit]:
    out: list[Hit] = []
    for m in RX["iban"].finditer(text):
        v = m.group(1).replace(" ", "")
        # B2 (measured, 12 Nov): 11,726 «IBAN», 483 passing mod-97 — the rest mostly securities' codes run into a word
        # («GB0007188757SEDOL», «XS…»). Kept: the valid ones, and the ones of a country's exact IBAN length (a real
        # IBAN read with a wrong character): 738, every valid one among them
        if len(v) >= 15 and (iban_ok(v) or IBAN_LENGTHS.get(v[:2], 0) == len(v)):
            out.append(Hit("iban", v, m.start(1), m.end(1), iban_ok(v)))
    for m in RX["bic"].finditer(text):
        v = m.group(1).upper()
        out.append(Hit("bic", v, m.start(1), m.end(1), bic_ok(v)))
    for m in RX["aba"].finditer(text):
        out.append(Hit("aba", m.group(1), m.start(1), m.end(1), aba_ok(m.group(1))))
    for m in RX["account"].finditer(text):
        v = re.sub(r"[\s-]", "", m.group(1))
        out.append(Hit("account", v, m.start(1), m.end(1), 6 <= len(v) <= 17))
    for m in RX["tail"].finditer(text):
        v = m.group(1)
        if not (TAIL_FORM.fullmatch(v) and len(v) <= 6):
            continue                                       # N0…, N00000, N0V: no registration has that form
        if len(v) < 4 and not FLYING.search(text[max(0, m.start() - 200): m.end() + 80]):
            continue
        out.append(Hit("tail", v, m.start(1), m.end(1), True))
    for m in RX["amount"].finditer(text):
        cur = m.group(1) or {"$": "USD", "€": "EUR", "£": "GBP"}[m.group(2)]
        out.append(Hit("amount", f"{cur} {m.group(3)}", m.start(), m.end(), True))
    for m in RX["coords"].finditer(text):
        lat, lon = float(m.group(1)), float(m.group(2))
        out.append(Hit("coords", f"{lat:.6f},{lon:.6f}", m.start(), m.end(), coords_ok(lat, lon)))
    for m in RX["dms"].finditer(text):
        lat, lon = _dms(*m.group(1, 2, 3, 4)), _dms(*m.group(5, 6, 7, 8))
        out.append(Hit("coords", f"{lat:.6f},{lon:.6f}", m.start(), m.end(), coords_ok(lat, lon)))
    return sorted(out, key=lambda h: h.start)


def masked(h: Hit) -> str:
    """How an answer shows a sensitive identifier (owner, 9 Nov: «la risposta sarà mascherata… le fonti in chiaro»):
    accounts and IBANs by their last four characters; the rest as found."""
    if h.kind in ("iban", "account"):
        return "…" + h.value[-4:]
    return h.value
