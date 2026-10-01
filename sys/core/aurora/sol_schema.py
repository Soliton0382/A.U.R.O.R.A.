# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The soliton: the unit of knowledge and memory of Aurora.

A soliton holds one piece of text exactly as it will be read and cited, plus
what is needed to trust it: its domain, where it comes from, its language, and
whether it is consolidated (LTM) or not yet (STM). It holds no vector: vectors
live in the index, which is rebuilt from the vault whenever the encoder changes.

Identity (`sid`, 32 hex characters, BLAKE2b-128):
- knowledge: hash of the normalized text. Identical text is the same fact and
  is stored once, whatever source brings it again.
- conversation / reflection: hash of kind, source_id, created_at and text. A
  turn is an event: the same words said twice at two moments are two solitons.

`sid` is the only key that joins the vault, the index and the logs. File names
never carry meaning.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TAXONOMY_FILE = Path(__file__).resolve().parents[1] / "config" / "taxonomy.json"
KINDS = ("knowledge", "conversation", "reflection")
MEMORY_KINDS = ("conversation", "reflection")
_LANG = re.compile(r"^[a-z]{2}$")
_SPACES = re.compile(r"[ \t  -​]+")
_BLANK_LINES = re.compile(r"\n{3,}")


def normalize(text: str) -> str:
    """Canonical form: Unicode NFC, LF newlines, single spaces, at most one blank line, trimmed."""
    t = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    t = "\n".join(_SPACES.sub(" ", line).strip() for line in t.split("\n"))
    return _BLANK_LINES.sub("\n\n", t).strip()


def _hash(data: str) -> str:
    return hashlib.blake2b(data.encode("utf-8"), digest_size=16).hexdigest()


def make_sid(kind: str, text: str, source_id: str = "", created_at: str = "") -> str:
    """Identity of a soliton; `text` must already be normalized."""
    if kind == "knowledge":
        return _hash(text)
    return _hash("\x1f".join((kind, source_id, created_at, text)))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def load_taxonomy(path: Path = TAXONOMY_FILE) -> dict[str, dict]:
    with open(path, encoding="utf-8") as f:
        domains = json.load(f)["domains"]
    return {d["id"]: d for d in domains}


@dataclass(frozen=True)
class Soliton:
    sid: str
    text: str
    domain: str
    kind: str
    lang: str
    source_id: str
    title: str
    chunk_index: int
    chunk_count: int
    consolidated: bool
    consolidated_at: str | None
    created_at: str
    schema_version: int
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def new(cls, text: str, domain: str, kind: str, lang: str, source_id: str, title: str = "",
            chunk_index: int = 0, chunk_count: int = 1, consolidated: bool | None = None,
            extra: dict[str, Any] | None = None, schema_version: int = 1,
            created_at: str | None = None) -> "Soliton":
        """Build a soliton from raw text. Knowledge is consolidated at birth; memory starts as STM."""
        body = normalize(text)
        created = created_at or now_iso()
        cons = (kind == "knowledge") if consolidated is None else consolidated
        return cls(sid=make_sid(kind, body, source_id, created), text=body, domain=domain, kind=kind,
                   lang=lang, source_id=source_id, title=normalize(title), chunk_index=chunk_index,
                   chunk_count=chunk_count, consolidated=cons,
                   consolidated_at=created if cons else None, created_at=created,
                   schema_version=schema_version, extra=dict(extra or {}))

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        row["consolidated"] = int(self.consolidated)
        row["extra"] = json.dumps(self.extra, ensure_ascii=False, sort_keys=True)
        return row

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Soliton":
        data = dict(row)
        data.pop("rowid", None)
        data["consolidated"] = bool(data["consolidated"])
        data["extra"] = json.loads(data["extra"] or "{}")
        return cls(**data)


def _is_iso(value: str | None) -> bool:
    if not value:
        return False
    try:
        return datetime.fromisoformat(value).tzinfo is not None
    except ValueError:
        return False


def validate(s: Soliton, taxonomy: dict[str, dict], min_chars: int = 0) -> list[str]:
    """Every problem of a soliton; an empty list means it can be stored."""
    p = []
    if not s.text:
        p.append("empty text")
    elif s.text != normalize(s.text):
        p.append("text is not normalized")
    if s.kind not in KINDS:
        p.append(f"kind {s.kind!r} not in {KINDS}")
    elif s.sid != make_sid(s.kind, s.text, s.source_id, s.created_at):
        p.append("sid does not match the content")
    if s.domain not in taxonomy:
        p.append(f"domain {s.domain!r} not in the taxonomy")
    elif s.kind in KINDS:
        memory_domain = bool(taxonomy[s.domain].get("memory"))
        if memory_domain != (s.kind in MEMORY_KINDS):
            p.append(f"kind {s.kind!r} does not belong in domain {s.domain!r}")
        elif s.kind in MEMORY_KINDS and s.domain != s.kind:
            p.append(f"a {s.kind} soliton belongs in domain {s.kind!r}")
    # The minimum drops the short tail of a document split into several chunks.
    # A complete document that is short by nature (a law article, an abstract)
    # is kept: the first version of this rule refused art. 1571 of the civil
    # code (183 characters), caught by the integration test.
    if s.kind == "knowledge" and min_chars and s.chunk_count > 1 and len(s.text) < min_chars:
        p.append(f"fragment of a multi-chunk document shorter than {min_chars} characters")
    if not _LANG.match(s.lang or ""):
        p.append(f"lang {s.lang!r} is not a two-letter ISO 639-1 code")
    if not s.source_id:
        p.append("missing source_id")
    if s.chunk_count < 1 or not 0 <= s.chunk_index < s.chunk_count:
        p.append(f"chunk {s.chunk_index}/{s.chunk_count} out of range")
    if not _is_iso(s.created_at):
        p.append("created_at is not an ISO timestamp with timezone")
    if s.consolidated and not _is_iso(s.consolidated_at):
        p.append("consolidated without consolidated_at")
    if not s.consolidated and s.consolidated_at is not None:
        p.append("consolidated_at set on a non-consolidated soliton")
    try:
        json.dumps(s.extra)
    except (TypeError, ValueError):
        p.append("extra is not JSON-serializable")
    return p
