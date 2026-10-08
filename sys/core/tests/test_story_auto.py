# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's videos on a schedule and the guard against repeated posts (owner, 2026-10-08)."""
import json
from types import SimpleNamespace

import pytest

from aurora import kno_story, kno_story_auto, sys_approvals, sys_routines, sys_social_guard


def test_a_post_repeating_one_of_the_last_days_is_recognised():
    old = [{"at": "07/10 18:31", "tool": "facebook.publish_post",
            "text": "🧬 La vita ha una «mano» preferita. Molti amminoacidi esistono in due forme speculari… "
                    "https://www.media.inaf.it/2026/10/07/x/\n\nGenerato con IA"}]
    same_link = "Un altro testo sugli amminoacidi https://www.media.inaf.it/2026/10/07/x/"
    reworded = "🧬 La vita ha una «mano» preferita! Molti amminoacidi esistono in due forme speculari e la vita ne usa una"
    other = "🌙 La Luna custodisce un segreto magnetico: il campione di suolo racconta un campo antico"
    drop = ("Generato con IA",)
    assert sys_social_guard.repeat_of(same_link, old, drop)
    assert sys_social_guard.repeat_of(reworded, old, drop)
    assert sys_social_guard.repeat_of(other, old, drop) is None


def test_the_guard_reads_what_went_out_by_aurora_or_approved_by_the_owner(cfg):
    a = sys_approvals.Approvals(cfg)
    act = {"plugin": "facebook", "tool": "publish_post", "arguments": {"message": "Perché il cielo è blu? La luce del sole"
                                                                                  " si diffonde nell'aria e il blu di più"}}
    a.record_auto("facebook.publish_post", "", act, "ok")
    assert sys_social_guard.check(cfg, act["arguments"]["message"]).startswith("REFUSED")
    assert sys_social_guard.check(cfg, "Cos'è un buco nero? Una regione dello spazio da cui nemmeno la luce esce") == ""


def test_a_video_is_made_only_from_public_sources():
    sols = {"a": SimpleNamespace(extra={"origin": "wikipedia", "url": "https://it.wikipedia.org/wiki/Laser"}),
            "b": SimpleNamespace(extra={"origin": "arxiv:2609.38016"}),
            "c": SimpleNamespace(extra={"origin": "patent"}),
            "d": SimpleNamespace(extra={"file": "mio.pdf"})}
    reader = SimpleNamespace(get_many=lambda sids: {s: sols[s] for s in sids if s in sols})
    public = [{"sid": "a", "title": "Laser"}, {"sid": "b", "title": "Paper"},
              {"sid": "w1", "title": "ESA", "source": "https://www.esa.int/kids"}]
    assert kno_story_auto.private_sources(reader, public) == []
    mixed = public + [{"sid": "c", "title": "Brevetto"}, {"sid": "d", "title": "Mio documento"}, {"sid": "x", "title": "?"}]
    assert kno_story_auto.private_sources(reader, mixed) == ["Brevetto", "Mio documento", "?"]


def test_topics_never_repeat_a_video_already_made():
    llm = SimpleNamespace(complete=lambda *a, **k: SimpleNamespace(
        answer='["Perché il cielo è blu?", "Cosa sono i neutrini?", "Come nasce una stella?"]'))
    assert kno_story_auto.topics(llm, "", ["Perché il cielo è blu?"]) == ["Cosa sono i neutrini?", "Come nasce una stella?"]


def _story(cfg, stamp, topic, auto=True):
    d = cfg.path("AURORA_IMAGE_DIR") / "stories" / stamp
    d.mkdir(parents=True)
    (d / f"aurora-{stamp}.mp4").write_bytes(b"x")
    (d / "script.json").write_text(json.dumps({"topic": topic, "length_s": 40}))
    (d / "post.txt").write_text(f"{topic}\n\nUn testo diverso per ogni video: {topic} spiegato in parole semplici.")
    if auto:
        (d / "auto.json").write_text(json.dumps({"made": 1, "published": None}))


class Host:
    def __init__(self):
        self.calls = []

    def plugins(self):
        man = {"social": {"label": "Facebook", "video": {"tool": "publish_video", "field": "message", "video": "video",
                                                         "format": "format", "default": "AURORA_FACEBOOK_VIDEO_AS"}}}
        return [SimpleNamespace(name="facebook", manifest=man, enabled=True, available=True, missing=[])]

    def call(self, plugin, tool, args, run_id=None):
        self.calls.append((plugin, tool, args))
        return {"ok": True, "text": "published as a Reel: video id 1"}


def test_the_oldest_ready_video_is_published_by_herself_within_the_day_s_number(cfg, monkeypatch):
    monkeypatch.setattr(sys_approvals, "social_auto", lambda c, action: True)
    _story(cfg, "20261008-033000", "Come nasce una stella?")
    _story(cfg, "20261008-043000", "Cosa sono i neutrini?")
    _story(cfg, "20261006-211705", "Fatto a mano dal proprietario", auto=False)
    host = Host()
    out = kno_story_auto.publish(cfg, host, lambda *a: None)
    assert "Come nasce una stella?" in out and host.calls[0][2]["video"] == "aurora-20261008-033000.mp4"
    assert [s["topic"] for s in kno_story_auto.ready(cfg)] == ["Cosa sono i neutrini?"]     # the owner's own: never


def test_beyond_the_day_s_number_the_video_waits_for_the_owner(cfg, monkeypatch):
    monkeypatch.setattr(sys_approvals, "social_auto", lambda c, action: False)
    _story(cfg, "20261008-033000", "Come nasce una stella?")
    host = Host()
    out = kno_story_auto.publish(cfg, host, lambda *a: None)
    assert "approvazione" in out and host.calls == []
    assert sys_approvals.Approvals(cfg).list("pending")[0]["title"] == "facebook.publish_video"
    assert kno_story_auto.ready(cfg) == []                         # waiting: not proposed twice


def test_a_story_routine_makes_or_publishes_and_nothing_else():
    ok = {"kind": "story", "action": "publish", "schedule": {"every": "custom", "times": ["11:00", "17:00"], "group": "all"}}
    assert sys_routines.validate(ok)["action"] == "publish"
    with pytest.raises(ValueError):
        sys_routines.validate({**ok, "action": "delete"})
    with pytest.raises(ValueError):
        sys_routines.validate({**ok, "format": "tiktok"})


def test_only_the_admin_schedules_videos():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "aurora" / "api" / "routines.py").read_text()
    assert 'body.get("kind") == "story" and me() != _admin()' in src


def test_make_checks_the_sources_before_painting(monkeypatch, cfg):
    painted = []
    ans = SimpleNamespace(abstained=False, mode="knowledge", sources=[{"sid": "c", "title": "Brevetto"}], text="x")
    pipe = SimpleNamespace(run=lambda *a, **k: ans, llm=None)
    monkeypatch.setattr("aurora.mdl_image.paint_many", lambda *a, **k: painted.append(1))
    with pytest.raises(ValueError, match="non pubbliche"):
        kno_story.make(pipe, cfg, "Un argomento", lambda *a: None, accept=lambda a: "fonti non pubbliche (Brevetto)")
    assert painted == []


def test_the_models_service_halves_its_batch_when_the_gpu_is_full(cfg):
    """C197: an out-of-memory batch is retried smaller instead of answering 500, and the batch size is restored. In a
    process of its own, as aurora-models is: torch never beside faiss (M145 — on a Mac two OpenMP runtimes in one
    process abort it, and the tests before this one loaded faiss)."""
    import subprocess
    import sys
    from pathlib import Path
    code = f"""
import sys
from pathlib import Path
sys.path.insert(0, "."); sys.path.insert(0, "script")
from aurora import sys_config
sys_config._cached = sys_config.load(Path({str(cfg.env_file)!r}), check_root=False)
import pytest, torch, svc_models as svc
svc.give_back = lambda: None
seen = []
class Model:
    batch = 8
    def encode(self, items):
        seen.append(self.batch)
        if self.batch > 2:
            raise torch.OutOfMemoryError("full")
        return len(items)
m = Model()
assert svc.shrinking(m, m.encode, ["a"] * 5) == 5
assert seen == [8, 4, 2] and m.batch == 8
m.encode = lambda items: (_ for _ in ()).throw(torch.OutOfMemoryError("always"))
with pytest.raises(torch.OutOfMemoryError):
    svc.shrinking(m, m.encode, ["a"])
assert m.batch == 8
print("ok")
"""
    r = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1], capture_output=True,
                       text=True, timeout=300)
    assert r.returncode == 0 and r.stdout.strip().endswith("ok"), r.stderr[-2000:]
