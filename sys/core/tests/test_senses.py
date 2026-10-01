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
