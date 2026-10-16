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


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_the_owner_speaking_over_her_interrupts_her_echo_and_a_cough_do_not():
    """Barge-in (owner, 2026-10-14: «la conversazione non è un ricevo tutto e poi ti rispondo»)."""
    echo, owner = [0.02] * 3, [0.15] * 10                             # her voice leaking at 0.02; the owner at 0.15
    cases = {"owner": echo + [0.02] * 5 + owner,                      # over 5× the echo for 0.4 s: she stops
             "echo": echo + [0.03] * 60,                              # her own voice a bit louder: never
             "cough": echo + [0.15] * 2 + [0.02] * 20}                # 0.2 s: not a turn
    out = json.loads(subprocess.run(["node", str(HERE / "js" / "vad_barge.mjs"), VAD.as_uri(), json.dumps(cases)],
                                    capture_output=True, text=True, check=True).stdout)
    assert out["owner"] == 1200                                       # 0.3 calibration + 0.5 echo + 0.4 voice
    assert out["echo"] == -1 and out["cough"] == -1


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_a_turn_begun_over_her_voice_is_heard_to_its_end():
    """C349: after a barge-in the owner is already speaking — a gate that calibrated on their voice heard nothing more
    and closed the turn at 8 s as «nothing said». Handed the barge-in's floor (her echo), it ends at the silence."""
    floor, owner = 0.02, [0.15] * 15
    cases = {"handed": {"from": {"floor": floor}, "levels": owner + [0.01] * 20},
             "calibrated_on_the_voice": owner + [0.01] * 100}
    out = json.loads(subprocess.run(["node", str(HERE / "js" / "vad_gate.mjs"), VAD.as_uri(), json.dumps(cases)],
                                    capture_output=True, text=True, check=True).stdout)
    assert out["handed"] == ["end", 300 + 1500 + 1200]             # the turn ends 1.2 s after the owner stops
    assert out["calibrated_on_the_voice"][0] == "nothing"            # what the old way did
