# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A document's identity: its collection and its number, read from the file's name.

A law office numbers the documents of a case (Bates numbers: a prefix and digits, «ABC0001234»); a public release
has its own scheme. The collections an installation knows are written in `docids.json` in the data folder
(EVD_DATA_DIR), never in the code:

    {"collections": [{"name": "ABC", "pattern": "^(ABC\\\\d{7})(?:_dup_\\\\d+)?$", "upper": true,
                      "official": "https://…/{number}.pdf"}]}

`pattern` is matched against the file name without its extension and its first group is the number; `upper` writes
the number in capitals; `official` (optional) is the address of the original, filled in only once verified on real
documents — never guessed. Without the file a generic Bates number is recognised (BATES); anything else keeps its
own name as its number (OTHER). A document's key is «collection:number»: an installation that changes its file
must re-key (evd_rekey.py), the passages being stored under the key."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

# a generic Bates number: a prefix of letters (and digits after the first), an optional separator, 4 to 10 digits
DEFAULT = [{"name": "BATES", "pattern": r"^([A-Z][A-Z0-9]{1,11}[-_]?\d{4,10})(?:_dup_\d+)?$", "upper": True}]
FILE = "docids.json"
_loaded: list[tuple[str, re.Pattern, bool]] | None = None
OFFICIAL: dict[str, str] = {}


def configure(collections: list[dict]) -> None:
    """Use these collections (a test, or the file read once)."""
    global _loaded
    loaded = []
    OFFICIAL.clear()
    for c in collections:
        name = str(c["name"]).upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,23}", name) or name == "OTHER":
            raise ValueError(f"docids: a collection's name: letters, digits, _ (not OTHER): {c['name']!r}")
        rx = re.compile(str(c["pattern"]), re.I)
        if rx.groups < 1:
            raise ValueError(f"docids: {name}'s pattern needs a group for the number")
        loaded.append((name, rx, bool(c.get("upper", True))))
        if c.get("official"):
            OFFICIAL[name] = str(c["official"])
    _loaded = loaded


def _collections() -> list[tuple[str, re.Pattern, bool]]:
    if _loaded is None:
        cols = DEFAULT
        try:
            from . import config
            f = config.load().path("EVD_DATA_DIR") / FILE
            if f.is_file():
                cols = json.loads(f.read_text(encoding="utf-8"))["collections"]
        except Exception:                               # noqa: BLE001 — no data folder yet: the generic numbers
            cols = DEFAULT
        configure(cols)
    return _loaded or []


@dataclass(frozen=True)
class DocId:
    collection: str          # a configured collection, BATES, or OTHER
    number: str              # the document's own number

    @property
    def key(self) -> str:
        return f"{self.collection}:{self.number}"

    def official_url(self) -> str | None:
        fmt = OFFICIAL.get(self.collection)
        return fmt.format(number=self.number) if fmt else None


def parse(path: str | Path) -> DocId:
    stem = Path(path).stem
    for collection, rx, upper in _collections():
        m = rx.match(stem)
        if m:
            return DocId(collection, m.group(1).upper() if upper else m.group(1))
    return DocId("OTHER", stem)


def cite(doc: DocId, page: int | None = None) -> str:
    """How an answer cites it: «ABC0001234 p. 3», with the official link when it is known."""
    where = f"{doc.number}" + (f" p. {page}" if page else "")
    url = doc.official_url()
    return f"{where} ({url})" if url else where
