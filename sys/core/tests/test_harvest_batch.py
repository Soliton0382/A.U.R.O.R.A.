# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A batch of arXiv papers asked from the Harvester page: only ids that can exist."""


def test_an_id_that_cannot_exist_is_said_not_asked():
    """13 Oct: «9999.99999» was asked of arXiv and stayed on the page («not found»), read as a count."""
    from aurora import kno_harvest as H
    ids, bad = H.parse_items("9999.99999\n2104.09864\nhttps://arxiv.org/abs/3001.00001")
    assert ids == ["2104.09864"] and len(bad) == 2 and all("impossibile" in b for b in bad)


def test_a_wikipedia_link_is_an_item_with_its_domain():
    from aurora import kno_harvest as H
    ids, bad = H.parse_items("https://en.wikipedia.org/wiki/Cold_fusion physics\nhttps://it.wikipedia.org/wiki/Friedrich_Nietzsche\n2104.09864")
    assert ids == ["wikipedia:en:Cold fusion@physics", "wikipedia:it:Friedrich Nietzsche@", "2104.09864"] and bad == []
