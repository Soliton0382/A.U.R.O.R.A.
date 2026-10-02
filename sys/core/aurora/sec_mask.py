# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""What may leave for a cloud model: the same text with personal and sensitive data replaced, and put back in the answer.

Every text sent to a cloud provider goes through a Pseudonymizer (AURORA_CLOUD_MASK, on by default): addresses (IPv4,
IPv6, MAC), e-mails, phone numbers, IBANs, card numbers, long tokens and keys, the value of every secret setting of
the .env, the owner's own words (name, domain, place, coordinates, AURORA_CLOUD_MASK_WORDS) and key=value fields that
name a user, a host or a device. Each becomes a placeholder like [IP_1], the same value always the same placeholder
within a conversation with the model, so the model can still reason about "the same address"; the answer is
unmasked before Aurora uses it. Pictures cannot be masked (faces, documents in a photo): a call that sends one is
counted and the owner is warned in the interface.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from . import sys_config

PATTERNS = [   # (kind, regex): order matters, the most specific first
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
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
PLACEHOLDER = re.compile(r"\[(EMAIL|IBAN|CARD|MAC|IP|IP6|PHONE|TOKEN|SECRET|PRIVATE|FIELD)_(\d+)\]")
BARE = re.compile(r"\b(EMAIL|IBAN|CARD|MAC|IP|IP6|PHONE|TOKEN|SECRET|PRIVATE|FIELD)_(\d+)\b")   # brackets dropped
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

    def mask(self, text: str) -> str:
        if not text:
            return text
        for v in self.secrets:                           # a secret's value, wherever it is
            if v in text:
                text = text.replace(v, self._ph("SECRET", v))
        text = FIELD.sub(lambda m: f"{m.group(1)}={self._ph('FIELD', m.group(2))}", text)
        for kind, rx in PATTERNS:
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
