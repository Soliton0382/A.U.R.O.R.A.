# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Ideas to improve Aurora (owner, 2026-10-06): kept, moved along, written as a developer reads them."""
import pytest

from aurora import sys_ideas as I


def test_an_idea_kept_moved_and_written(cfg):
    it = I.add(cfg, {"areas": ["security", "nonsense"], "kind": "feature", "priority": "high", "title": "Mappa disegnata",
                     "text": "Un bottone che apre la mappa della rete."})
    assert it["areas"] == ["security"] and it["state"] == "new" and I.listing(cfg)[0]["id"] == it["id"]
    I.update(cfg, it["id"], {"state": "done", "note": "M115"})
    md = I.as_markdown(I.listing(cfg)[0])
    assert md.startswith("### 💡 Mappa disegnata") and "priorità: high" in md and "stato: done" in md and "Nota: M115" in md
    with pytest.raises(ValueError):
        I.add(cfg, {"title": " ", "text": ""})
    with pytest.raises(ValueError):
        I.update(cfg, it["id"], {"state": "maybe"})
