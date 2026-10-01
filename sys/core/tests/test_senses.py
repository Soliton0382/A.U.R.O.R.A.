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
