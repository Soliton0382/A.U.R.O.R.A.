# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C344: a cloud model's stream went through the fallback gathered whole (list), so the chat showed every piece at the
end and nothing could be spoken while written. Now each piece goes on at once; a failure before the first falls back
in silence, one after some is said and the local model answers whole."""
from aurora import mdl_router as R


class Model:
    name, model = "cloud", "m"

    def __init__(self, pieces, fail_after=None):
        self.pieces, self.fail_after, self.given = pieces, fail_after, 0

    def stream(self, system, user, max_tokens, think=False):
        for i, p in enumerate(self.pieces):
            if self.fail_after is not None and i == self.fail_after:
                raise RuntimeError("connection reset")
            self.given += 1
            yield "answer", p


def test_each_piece_goes_on_before_the_next_is_made():
    cloud = Model(["Ciao", ", ", "amico."])
    f = R.Fallback(cloud, Model(["locale"]), "self")
    out = f.stream("s", "Come stai?", 100)
    assert next(out) == ("answer", "Ciao") and cloud.given == 1        # the first piece, not the whole answer
    assert [p for _, p in out] == [", ", "amico."]


def test_a_cloud_down_at_once_is_the_local_model_in_silence():
    f = R.Fallback(Model(["x"], fail_after=0), Model(["Sto bene."]), "self")
    assert list(f.stream("s", "Come stai?", 100)) == [("answer", "Sto bene.")]


def test_a_cloud_down_halfway_is_said_and_the_local_model_answers_whole():
    f = R.Fallback(Model(["Allora", " domani"], fail_after=1), Model(["Domani piove."]), "self")
    out = [p for _, p in f.stream("s", "Che tempo farà domani?", 100)]
    assert out[0] == "Allora" and "⚠️" in out[1] and "locale" in out[1] and out[2] == "Domani piove."
