# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import io

import pytest
from PIL import Image

from aurora.kno_attach import classify, is_image, to_jpeg


class FakeLLM:
    def __init__(self, reply):
        self.reply = reply

    def complete(self, system, user, max_tokens, think=False):
        return type("C", (), {"answer": self.reply})()


def test_is_image():
    assert is_image("x.PNG") and is_image("foto", "image/heic") and not is_image("a.pdf", "application/pdf")


def test_to_jpeg_scales_and_converts():
    buf = io.BytesIO()
    Image.new("RGBA", (3000, 1500), (10, 20, 30, 128)).save(buf, "PNG")
    out = Image.open(io.BytesIO(to_jpeg(buf.getvalue(), 1024)))
    assert out.format == "JPEG" and out.mode == "RGB" and out.size == (1024, 512)


@pytest.mark.parametrize("reply,expected", [("physics", "physics"), ("law_it.", "law_it"),
                                            ("conversation", "general"), ("", "general"), ("banana", "general")])
def test_classify_accepts_only_knowledge_domains(reply, expected):
    assert classify(FakeLLM(reply), "doc.txt", "testo") == expected
