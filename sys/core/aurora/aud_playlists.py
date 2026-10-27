# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The player's playlists, folders of tracks (owner, 28 Oct: «sai cosa manca nel lettore amp? la gestione in cartelle
dei brani, tipo play list»).

A user's lists in their music folder (playlists.json, 0600): each {"id", "name", "items"} where an item is what the
mixer takes — a track's name, or «mixes/<name>» for a song, a remix, a mix or a set. A track deleted leaves every list
(pruned when read); the order of the items is the order they play in. The folders by kind (sung by Aurora, yours,
mixes, sets) are the page's own: nothing to keep.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path

FILE = "playlists.json"
MAX_LISTS, MAX_ITEMS, NAME_MAX = 100, 2000, 60
REF = re.compile(r"(?:mixes/)?[\w\- .()'àèéìòù]{1,120}\.(mp3|wav|flac|ogg|m4a|aac|opus|webm)", re.I)
ID = re.compile(r"[0-9a-f]{8}")


def load(folder: Path, have: set[str] | None = None) -> list[dict]:
    """The lists, their items still there when `have` (the refs of the tracks present) is given."""
    try:
        lists = json.loads((folder / FILE).read_text(encoding="utf-8")).get("lists", [])
    except (OSError, ValueError, AttributeError):
        return []
    out = []
    for p in lists if isinstance(lists, list) else []:
        if isinstance(p, dict) and ID.fullmatch(str(p.get("id", ""))):
            items = [r for r in p.get("items", []) if isinstance(r, str) and (have is None or r in have)]
            out.append({"id": p["id"], "name": str(p.get("name", ""))[:NAME_MAX], "items": items})
    return out


def check(lists) -> list[dict]:
    """The lists as sent by the page, checked: a name, items that are track refs (each once), an id kept or made."""
    if not isinstance(lists, list) or len(lists) > MAX_LISTS:
        raise ValueError(f"lists: at most {MAX_LISTS}")
    out, ids = [], set()
    for p in lists:
        if not isinstance(p, dict):
            raise ValueError("a list: {name, items}")
        name = " ".join(str(p.get("name", "")).split())[:NAME_MAX]
        if not name:
            raise ValueError("a list needs a name")
        items = p.get("items", [])
        if not isinstance(items, list) or len(items) > MAX_ITEMS or not all(isinstance(r, str) and REF.fullmatch(r) for r in items):
            raise ValueError(f"items: track names (mixes/<name> for a mix), at most {MAX_ITEMS}")
        pid = str(p.get("id") or "")
        if not ID.fullmatch(pid) or pid in ids:
            pid = uuid.uuid4().hex[:8]
        ids.add(pid)
        out.append({"id": pid, "name": name, "items": list(dict.fromkeys(items))})
    return out


def save(folder: Path, lists) -> list[dict]:
    good = check(lists)
    f = folder / FILE
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps({"lists": good}, ensure_ascii=False, indent=1), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(f)
    return good
