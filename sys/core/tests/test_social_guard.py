# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C728: the guard against repeated posts sees the posts waiting or rejected, and a subject told again in other words.
Every text here is invented."""
import itertools
import json
from pathlib import Path

from aurora import sys_approvals, sys_social_guard as G

DATA = Path(__file__).parent / "data" / "social_posts_c728.json"
DROP = ("Generato con IA",)


def _post(text):
    return {"plugin": "facebook", "tool": "publish_post", "arguments": {"message": text}}


def test_a_post_waiting_or_rejected_counts_and_the_agent_is_told_which(cfg):
    a = sys_approvals.Approvals(cfg)
    waiting = a.request("tool_call", "external", "facebook.publish_post", "", {}, _post(
        "🐝 Le api sanno contare\nIn un esperimento le api hanno imparato a scegliere il cartoncino con meno simboli"))
    no = a.request("tool_call", "external", "facebook.publish_post", "", {}, _post(
        "☄️ Una cometa venuta da un'altra stella\nUna cometa interstellare attraversa il Sistema solare su un'orbita "
        "iperbolica: la sua chioma ha più monossido di carbonio delle comete nostrane"))
    a.update(no["id"], status="rejected")
    failed = a.request("tool_call", "external", "facebook.publish_post", "", {}, _post(
        "🧲 Un superconduttore a strati sottili\nIn un materiale di strati atomici ruotati la corrente scorre senza "
        "resistenza elettrica"))
    a.update(failed["id"], status="failed")                        # it never went out, nobody said no to it
    assert {p["status"] for p in G.recent(cfg)} == {"pending", "rejected"}
    assert "waits for the owner's approval" in G.check(cfg, waiting["action"]["arguments"]["message"])
    again = ("Un visitatore da un altro sistema planetario\nSu un'orbita iperbolica, senza ritorno, una cometa "
             "interstellare passa vicino al Sole: la chioma è ricca di monossido di carbonio, più delle comete nostrane")
    assert "the owner already rejected this subject" in G.check(cfg, again)
    assert G.check(cfg, failed["action"]["arguments"]["message"]) == ""


def test_the_same_title_over_another_text_is_a_repeat():
    old = [{"at": "20/11 08:30", "tool": "facebook.publish_post",
            "text": "Il segreto dei tardigradi svelato\nUna proteina avvolge il loro DNA e lo protegge dai danni."}]
    assert G.repeat_of("Il segreto dei tardigradi svelato!\nResistono al vuoto e al gelo, e ora sappiamo perché.", old)
    assert G.repeat_of("Il segreto delle api\nRiconoscono lo zero in un esperimento con cartoncini e simboli.",
                       old) is None


def test_the_tuning_set_keeps_its_numbers():
    """The numbers of the tuning (M327): rewordings of one subject against different subjects of the same fields."""
    topics = json.loads(DATA.read_text(encoding="utf-8"))["topics"]
    posts = [(t["id"], p + "\n\n" + DROP[0]) for t in topics for p in t["posts"]]
    missed = taken = 0
    for (sa, a), (sb, b) in itertools.permutations(posts, 2):     # a new post against one of the days before
        hit = G.repeat_of(a, [{"text": b}], DROP) is not None
        missed += sa == sb and not hit
        taken += sa != sb and hit
    assert (len(posts), missed, taken) == (44, 2, 0)
    for t in topics:                                              # told a third time, every subject is seen
        for i, p in enumerate(t["posts"]):
            assert G.repeat_of(p, [{"text": q} for j, q in enumerate(t["posts"]) if j != i], DROP)
