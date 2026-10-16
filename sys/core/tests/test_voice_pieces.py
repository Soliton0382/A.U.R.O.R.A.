# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's own voice, sentence by sentence (ROADMAP 99 step 3, M211): the first piece is one sentence, heard at once;
the rest in pieces of whole sentences up to 400 characters; nothing lost."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
VOICE = HERE.parent / "webui" / "js" / "voice.js"


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_the_first_sentence_alone_then_whole_sentences():
    s = "Un solitone è un'onda solitaria che conserva la forma. Nasce dall'equilibrio tra dispersione e non linearità. "
    long_text = (s * 8).strip()
    out = json.loads(subprocess.run(["node", str(HERE / "js" / "voice_pieces.mjs"), VOICE.as_uri(),
                                     json.dumps([long_text, "Ciao!", "Una frase sola senza punto"])],
                                    capture_output=True, text=True, check=True).stdout)
    first, short, bare = out
    assert first[0] == "Un solitone è un'onda solitaria che conserva la forma."
    assert all(len(p) <= 400 for p in first[1:]) and len(first) >= 3
    assert " ".join(first).replace("  ", " ") == long_text                     # nothing lost, nothing added
    assert short == ["Ciao!"] and bare == ["Una frase sola senza punto"]


def _stream(mode: str, tokens: list[str]):
    return json.loads(subprocess.run(["node", str(HERE / "js" / "voice_stream.mjs"), VOICE.as_uri(), mode, json.dumps(tokens)],
                                     capture_output=True, text=True, check=True, timeout=30).stdout)


def _tokens(text: str, n: int = 4) -> list[str]:
    return [text[i:i + n] for i in range(0, len(text), n)]


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_a_streamed_answer_is_cut_at_whole_sentences_only():
    text = ("Ciao! Domani sera il cielo è sereno, 3.5 gradi alle 22. Ecco i passi:\n\n1. Monta la testa.\n2. Bilancia. "
            "Il codice:\n```\nx = 1. y = 2.\n```\nFine del discorso.")
    out = _stream("feed", _tokens(text))
    assert "".join(out) == text                                                 # nothing lost, nothing added
    assert out[0].startswith("Ciao! Domani sera")                               # «Ciao!» alone is too short to go
    assert not any("3." == o.strip()[-2:] for o in out) and all("```" not in o or o.count("```") == 2 for o in out)
    assert not any(o.strip() in ("1.", "2.") for o in out)                      # a list's number waits for its item


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_the_first_sentence_is_heard_while_the_rest_is_written():
    s = "Il cielo domani sera sarà limpido fino a mezzanotte. "
    text = s + "".join(f"Poi, verso le {h}, arriva qualche velatura da ovest, ma il seeing resta discreto. " for h in (23, 24, 1)) \
        + "Buona serata!"                                    # all different: a clip already made is not made again
    out = _stream("speak", _tokens(text))
    assert out["r"] == "ok"
    heard = [h[0] for h in out["heard"]]
    assert heard[0] == s.strip() and " ".join(heard).replace("  ", " ") == text   # in order, all of it
    assert out["heard"][0][1] < out["ended"]                                    # heard before the answer was finished
    assert len(out["made"]) == len(heard) and all(len(h) <= 400 for h in heard)
