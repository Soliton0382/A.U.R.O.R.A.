# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""What may leave for a cloud model: the same text with personal and sensitive data replaced, and put back in the answer.

Every text sent to a cloud provider goes through a Pseudonymizer, always (no setting turns it off): addresses (IPv4,
IPv6, MAC), e-mails, phone numbers, IBANs, card numbers, long tokens and keys, the value of every secret setting of
the .env, the owner's own words (name, domain, place, coordinates, AURORA_CLOUD_MASK_WORDS), key=value fields that
name a user, a host or a device; and (2026-10-05) private keys, signed tokens (JWT), a password in a link, the Italian
tax code, VAT number, car plates, street addresses, and any value said by its name (password, PIN, tax code, passport,
identity card, driving licence, health card, date of birth). Each becomes a placeholder like [IP_1], the same value always the same placeholder
within a conversation with the model, so the model can still reason about "the same address"; the answer is
unmasked before Aurora uses it. Pictures cannot be masked (faces, documents in a photo): a call that sends one is
counted and the owner is warned in the interface.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from . import sys_config

# whole blocks and credentials first: a private key, a signed token, a password in a link (owner, 2026-10-05)
BLOCKS = [
    ("KEY", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("CRED", re.compile(r"(?<=://)[^\s/:@]+:[^\s/@]+(?=@)")),           # user:password@ in a link
]
# a value said by its name: "password: x", "codice fiscale RSSMRA...", "nato il 3/4/1980", "patente U1234567"
CONTEXT = re.compile(
    r"(?i)\b(password|passwd|pwd|passphrase|pin|puk|otp|codice fiscale|c\.f\.|partita iva|p\.\s?iva|vat(?: number)?|"
    r"passaporto|passport(?: number)?|carta d'identit[aà]|identity card|patente|driving licen[cs]e|tessera sanitaria|"
    r"nato il|nata il|data di nascita|date of birth|born on|born)\s*(?::|=|n\.|nr\.?|is)?\s*"
    r"(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{1,2} \w+ \d{4}|[^\s,;]{3,64})")
PATTERNS = [   # (kind, regex): order matters, the most specific first
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("CF", re.compile(r"\b[A-Z]{6}\d{2}[A-EHLMPRST]\d{2}[A-Z]\d{3}[A-Z]\b", re.I)),     # Italian tax code
    ("VAT", re.compile(r"\bIT ?\d{11}\b")),                                               # Italian VAT with prefix
    ("ADDRESS", re.compile(r"(?i)\b(?:via|viale|piazza|piazzale|corso|largo|vicolo|strada|contrada|localit[aà]|"
                           r"street|avenue|road)\s+(?:[A-Za-zÀ-ú'.]+\s+){0,4}?[A-Za-zÀ-ú'.]+,?\s*\d{1,4}[a-zA-Z]?\b")),
    ("PLATE", re.compile(r"\b[A-Z]{2} ?\d{3} ?[A-Z]{2}\b")),                              # Italian car plate
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,7}(?: ?[A-Z0-9]{1,4})?\b")),
    ("CARD", re.compile(r"\b(?:\d[ -]?){13,16}\d\b")),
    ("MAC", re.compile(r"\b[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}\b")),
    ("IP", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("IP6", re.compile(r"\b(?:[0-9a-fA-F]{1,4}:){4,7}[0-9a-fA-F]{1,4}\b")),
    ("PHONE", re.compile(r"(?<![\w.+])(?:\+\d{1,3}[ .-]?\d{2,4}(?:[ .-]?\d{2,4}){1,4}|\d{2,4}(?:[ .]\d{2,4}){2,4})(?!\w|\.\d)")),
    ("TOKEN", re.compile(r"\b(?=[A-Za-z0-9_\-]*\d)(?=[A-Za-z0-9_\-]*[A-Za-z])[A-Za-z0-9_\-]{32,}\b|\b[0-9a-fA-F]{24,}\b")),
]
FIELD = re.compile(r'\b(\w*(?:serial|user|username|login|account|host|hostname|mac|email|domain|device_name)\w*)='
                   r'("[^"]*"|\S+)', re.I)
KINDS = "EMAIL|IBAN|CARD|MAC|IP|IP6|PHONE|TOKEN|SECRET|PRIVATE|FIELD|KEY|JWT|CRED|ID|CF|VAT|ADDRESS|PLATE"
PLACEHOLDER = re.compile(rf"\[({KINDS})_(\d+)\]")
BARE = re.compile(rf"\b({KINDS})_(\d+)\b")   # brackets dropped
KEEP = ("\n\nSome private data in this text was replaced by placeholders in square brackets, like [IP_1] or [EMAIL_2]: "
        "write them back exactly as they are, brackets included; never explain, translate or change them.")


def luhn(number: str) -> bool:
    d = [int(c) for c in number if c.isdigit()]
    if not 13 <= len(d) <= 19:
        return False
    total = sum(d[-1::-2]) + sum(sum(divmod(2 * x, 10)) for x in d[-2::-2])
    return total % 10 == 0


class Pseudonymizer:
    """Reversible masking for one conversation with a cloud model (keep one instance per call or per agent run)."""

    def __init__(self, cfg: sys_config.Config | None = None):
        cfg = cfg or sys_config.get()
        self.to_ph: dict[str, str] = {}
        self.to_val: dict[str, str] = {}
        self.counts: Counter = Counter()
        own = [str(cfg.values.get(k) or "") for k in ("AURORA_OWNER_NAME", "AURORA_DOMAIN", "AURORA_WEATHER_PLACE",
                                                       "AURORA_WEATHER_LAT", "AURORA_WEATHER_LON")]
        dom = str(cfg.values.get("AURORA_DOMAIN") or "")
        if dom.count(".") >= 1:
            own.append(".".join(dom.split(".")[-2:]))
        own += [w.strip() for w in str(cfg.values.get("AURORA_CLOUD_MASK_WORDS") or "").split(",")]
        user = Path.home().name
        if len(user) >= 3:
            own.append(f"/home/{user}")
        self.private = sorted({w for w in own if len(w) >= 3 and w.lower() not in ("localhost", "auto")}, key=len, reverse=True)
        secrets = []
        for s in sys_config.load_schema()["settings"]:
            v = str(cfg.values.get(s["key"]) or "")
            if s.get("secret") and len(v) >= 8 and v != "redacted":
                secrets.append(v)
        self.secrets = sorted(set(secrets), key=len, reverse=True)

    def _ph(self, kind: str, value: str) -> str:
        if value in self.to_ph:
            return self.to_ph[value]
        n = sum(1 for p in self.to_val if p.startswith(f"[{kind}_")) + 1
        ph = f"[{kind}_{n}]"
        self.to_ph[value], self.to_val[ph] = ph, value
        self.counts[kind] += 1
        return ph

    def mask(self, text: str, skip: frozenset = frozenset()) -> str:
        """`skip`: kinds left as they are (the forge keeps its own format-preserving stand-ins for addresses)."""
        if not text:
            return text
        for v in self.secrets:                           # a secret's value, wherever it is
            if v in text:
                text = text.replace(v, self._ph("SECRET", v))
        for kind, rx in BLOCKS:
            text = rx.sub(lambda m, k=kind: m.group(0) if PLACEHOLDER.fullmatch(m.group(0)) else self._ph(k, m.group(0)), text)
        text = CONTEXT.sub(lambda m: m.group(0) if PLACEHOLDER.fullmatch(m.group(2))
                           else m.group(0)[: m.start(2) - m.start(0)] + self._ph("ID", m.group(2)), text)
        text = FIELD.sub(lambda m: f"{m.group(1)}={self._ph('FIELD', m.group(2))}", text)
        for kind, rx in PATTERNS:
            if kind in skip:
                continue

            def rep(m, k=kind):
                v = m.group(0)
                if PLACEHOLDER.fullmatch(v) or (k == "CARD" and not luhn(v)) \
                        or (k == "PHONE" and sum(c.isdigit() for c in v) < 9):
                    return v                             # a long number that is not a card, a date that is not a phone
                return self._ph(k, v)
            text = rx.sub(rep, text)
        for w in self.private:                           # the owner's own words, case kept as written
            if w in text:
                text = text.replace(w, self._ph("PRIVATE", w))
        return text

    def unmask(self, text: str) -> str:
        """The model's answer with the real values back (a placeholder it invented stays as it is)."""
        text = PLACEHOLDER.sub(lambda m: self.to_val.get(m.group(0), m.group(0)), text or "")
        # a model that dropped the brackets (C86): only the placeholders made in this conversation come back
        return BARE.sub(lambda m: self.to_val.get(f"[{m.group(0)}]", m.group(0)), text)

    def unmask_stream(self, pieces):
        """Unmask a stream of text pieces: a placeholder may arrive split across two pieces."""
        buf = ""
        for kind, piece in pieces:
            if kind != "answer":
                yield kind, piece
                continue
            buf += piece
            cut = buf.rfind("[")
            if cut >= 0 and "]" not in buf[cut:] and len(buf) - cut < 24:
                out, buf = buf[:cut], buf[cut:]
            else:
                out, buf = buf, ""
            if out:
                yield "answer", self.unmask(out)
        if buf:
            yield "answer", self.unmask(buf)
