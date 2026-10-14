# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Emoji are not read aloud (owner, 14 Oct: «sentire "stelline" fa ridere»)."""
from aurora.mdl_tts import EMOJI


def test_emoji_go_words_stay():
    text = "✨ Buongiorno! 🌙 Stanotte ho studiato 3 paper ⭐⭐ e ho sognato 🇮🇹 ❤️ 1️⃣ fine."
    out = " ".join(EMOJI.sub(" ", text).split())
    assert out == "Buongiorno! Stanotte ho studiato 3 paper e ho sognato 1 fine."
