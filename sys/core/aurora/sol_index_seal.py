# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The sealed vector file's integrity tag and its second format (C572, 12 Nov).

A user's memory vectors are AES-CTR under the manifest's nonce, the counter the byte's place in the file (sol_index).
Two gaps of that first format:
 - an update interrupted after the bytes were appended and before the manifest was saved left bytes that the next
   update cut and wrote again — other rows under the same keystream. Whoever kept the cut bytes (a snapshot, a
   backup, a local reader) had the XOR of two plaintexts;
 - nothing said the file was the one written: CTR lets a bit be flipped where one wants.
Format 2 (manifest «sealed»: {"user", "nonce", "v": 2, "mac"}): the same bytes on disk, plus an HMAC-SHA256 over the
nonce, the width, the ciphertext and the row count, keyed from the user's own «memory_index» key; a file cut back is
sealed again whole under a new nonce (sol_index). A file of format 1 is read as it is and gets its tag at the next
update, with nothing written again: no vector is lost, none encoded twice. A tag that does not match is never
trusted: the index is derived data, the Indexer builds it again from the sealed memory.
"""
from __future__ import annotations

import hashlib
import hmac
from pathlib import Path

from . import sys_config

VERSION = 2
PIECE = 1 << 20


class Tampered(Exception):
    """A sealed vector file that is not the one its manifest's tag was made for."""


def _mac_key(cfg: sys_config.Config, user: str | None) -> bytes:
    from . import sys_seal                             # from the user's own key: no second key file to keep or lose
    return hmac.new(sys_seal._key(cfg, user or None, "memory_index"), b"aurora-index-mac-v2", hashlib.sha256).digest()


class Tag:
    """The tag as the file grows: fed with the ciphertext in order, asked at any row count (an append costs its own
    bytes, not the whole file again)."""

    def __init__(self, cfg: sys_config.Config, sealed: dict, dim: int):
        self.h = hmac.new(_mac_key(cfg, sealed.get("user")), digestmod=hashlib.sha256)
        self.h.update(b"aurora-index-v2|" + bytes.fromhex(sealed["nonce"]) + int(dim).to_bytes(4, "big"))

    def feed(self, data: bytes) -> "Tag":
        self.h.update(data)
        return self

    def at(self, count: int) -> str:
        h = self.h.copy()
        h.update(b"|" + int(count).to_bytes(8, "big"))
        return h.hexdigest()


def of_bytes(cfg: sys_config.Config, raw: bytes, m: dict) -> str:
    return Tag(cfg, m["sealed"], m["dim"]).feed(raw).at(m["count"])


def tagged(m: dict) -> bool:
    return bool((m.get("sealed") or {}).get("mac"))


def check(cfg: sys_config.Config, raw: bytes, m: dict) -> None:
    """Tampered when a tagged file's bytes are not the tagged ones; a file of format 1 (no tag yet) passes."""
    if tagged(m) and not hmac.compare_digest(of_bytes(cfg, raw, m), str(m["sealed"]["mac"])):
        raise Tampered(f"sealed vectors: the file is not the one its manifest was written for ({m['count']} rows)")


def stamp(m: dict, mac: str) -> None:
    m["sealed"] = {**m["sealed"], "v": VERSION, "mac": mac}


def fresh(user: str) -> dict:
    """A new nonce for a file written whole (never the one before: the keystream is used once)."""
    import os
    return {"user": user, "nonce": os.urandom(16).hex()}
