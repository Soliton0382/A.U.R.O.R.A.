# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""SSCC on the reading path too (owner, 13 Oct: «sscc deve funzionare per aiutare a risparmiare token… uno può decidere
se averlo attivo oppure no»): the texts sent to a cloud reader are compressed, a local reader's never, and the switch
turns it off."""
from types import SimpleNamespace

from aurora import kno_read

LONG = " ".join(f"Frase numero {i} parla di argomenti vari e lontani dalla domanda posta." for i in range(20)) + \
       " Il punto di ebollizione dell'acqua in alta quota è più basso perché la pressione è minore."


def _p(cloud: bool, on: bool = True):
    local = object()
    return SimpleNamespace(cfg={"AURORA_CLOUD_COMPRESSION": on, "AURORA_CLOUD_KEEP_PCT": 60}, llm=local,
                           _for=lambda role: object() if cloud else local)


def test_a_cloud_reader_gets_the_salient_sentences_a_local_one_everything():
    texts = [{"text": LONG, "source": {"title": "t"}}]
    q = "Perché l'acqua bolle a una temperatura più bassa in alta quota?"
    out = kno_read._for_cloud(_p(cloud=True), q, texts)[0]["text"]
    assert len(out) < len(LONG) and "ebollizione" in out                  # shorter, the answering sentence kept
    assert kno_read._for_cloud(_p(cloud=False), q, texts)[0]["text"] == LONG
    assert kno_read._for_cloud(_p(cloud=True, on=False), q, texts)[0]["text"] == LONG
