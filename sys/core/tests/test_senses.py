# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
from aurora import sns_av


def test_whisper_inventions_on_silence_are_not_speech():
    assert not sns_av.clear_speech("Grazie.")
    assert not sns_av.clear_speech(" Thank you. ")
    assert not sns_av.clear_speech("はい" * 30)
    assert not sns_av.clear_speech("la la la la la la la la la la")
    assert not sns_av.clear_speech("")
    assert sns_av.clear_speech("Aurora, stanotte ho fotografato la nebulosa di Orione.")
    assert sns_av.clear_speech("Grazie Aurora, ottimo lavoro con la guida.")


def test_a_device_chosen_by_the_owner_wins_over_auto():
    assert sns_av._pick("/dev/video3", [{"id": "/dev/video0"}], "camera") == "/dev/video3"
    assert sns_av._pick("auto", [{"id": "/dev/video0"}, {"id": "/dev/video2"}], "camera") == "/dev/video0"


def test_audio_from_a_phone_is_decoded_whatever_its_container(cfg, tmp_path):
    """WebM/Opus (Android) and MP4/AAC with the index at the end (iOS) both become 16 kHz mono."""
    import subprocess

    import pytest

    from aurora import sns_av
    for name, codec in (("a.webm", ["-c:a", "libopus"]), ("i.m4a", ["-c:a", "aac"])):
        f = tmp_path / name
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                        *codec, str(f)], check=True)
        audio = sns_av.decode(f.read_bytes(), cfg)
        assert 1.9 * 16000 < len(audio) < 2.1 * 16000 and audio.dtype.name == "float32"
    with pytest.raises(ValueError):
        sns_av.decode(b"not audio at all", cfg)


def test_speech_to_text_is_asked_of_the_models_service_never_run_here(cfg, monkeypatch):
    """M145: torch beside faiss in the API's process put two OpenMP runtimes in one process (fatal on a Mac): Whisper
    runs in aurora-models (mdl_stt); sns_av sends the audio there, raw 16 kHz float32."""
    import numpy as np
    from pathlib import Path
    seen = {}

    class Answer:
        def raise_for_status(self):
            return None

        def json(self):
            return seen["answer"]

    def post(url, params, content, headers, timeout):
        seen.update(url=url, lang=params["lang"], n=len(content), ctype=headers["Content-Type"])
        return Answer()
    monkeypatch.setattr("httpx.post", post)
    seen["answer"] = {"text": "ciao", "clear": True, "seconds": 0.4, "audio_s": 1.0}
    assert sns_av.transcribe(np.zeros(16000, dtype=np.float64), "it", cfg)["text"] == "ciao"
    assert seen["url"].endswith("/transcribe") and seen["n"] == 16000 * 4 and seen["lang"] == "it"
    seen["answer"] = [[0.0, 2.5, "una frase"]]
    assert sns_av.transcribe_segments(np.zeros(8000, dtype=np.float32), "en", cfg) == [(0.0, 2.5, "una frase")]
    assert seen["url"].endswith("/transcribe/segments")
    src = (Path(sns_av.__file__)).read_text(encoding="utf-8")
    assert "import torch" not in src and "transformers" not in src
