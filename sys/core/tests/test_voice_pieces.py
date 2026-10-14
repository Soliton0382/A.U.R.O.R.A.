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
