# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""When the owner stops speaking (webui/js/vad.js, ROADMAP 99): the turn ends after 1.2 s of quiet that follows speech;
no speech in 8 s is nothing said; a noisy room raises the threshold."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
VAD = HERE.parent / "webui" / "js" / "vad.js"


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_the_silence_gate():
    room, voice = [0.002] * 3, [0.08] * 15
    cases = {"spoke": room + voice + [0.003] * 20,                    # speech, then 1.2 s quiet: the turn ends
             "pause": room + voice + [0.003] * 8 + voice + [0.003] * 13,   # a short pause is not the end
             "silent": room + [0.003] * 100,                          # nobody spoke: nothing, at 8 s
             "noisy": [0.03] * 3 + [0.05] * 100}                      # a fan at 0.05: under 3× its floor, not speech
    out = json.loads(subprocess.run(["node", str(HERE / "js" / "vad_gate.mjs"), VAD.as_uri(), json.dumps(cases)],
                                    capture_output=True, text=True, check=True).stdout)
    assert out["spoke"] == ["end", 3000]                      # 0.3 s calibration + 1.5 s voice + 1.2 s quiet
    assert out["pause"][0] == "end" and out["pause"][1] > 3800
    assert out["silent"] == ["nothing", 8000]
    assert out["noisy"] == ["nothing", 8000]
