# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N64 phase 5: a user's status files that hold a chat's content are sealed with the user's key. For each one: the file
on disk holds none of a made-up value, its reader gives it back, and a file written before N64 (plaintext) still reads.
Every value here is invented."""
import json
import sqlite3
import time
from contextlib import closing

import numpy as np

from aurora import sys_push, sys_seal

SECRET = "Zanzibar violetto 4417"
REMEMBER, SEND = sys_push.remember, sys_push.send   # the real ones: the tests' fixture replaces them (conftest)


def _clean(path) -> bool:
    """None of the made-up value in the file's bytes, nor in a sqlite file's pages."""
    return SECRET.encode() not in path.read_bytes() and b"Zanzibar" not in path.read_bytes()


def test_review_and_study_outcomes_are_sealed(cfg):
    from aurora import kno_review, kno_study
    for mod in (kno_review, kno_study):
        mod._mark(cfg, "run-1", {"question": SECRET, "at": 1.0})
        f = mod._state_file(cfg)
        assert _clean(f) and sys_seal.is_sealed(f.read_bytes())
        assert mod._done(cfg) == {"run-1": {"question": SECRET, "at": 1.0}}
        f.write_text(json.dumps({"old": {"question": "di prima"}}))      # a file of before
        assert mod._done(cfg) == {"old": {"question": "di prima"}}
        mod._mark(cfg, "run-2", {"question": SECRET})
        assert _clean(f) and set(mod._done(cfg)) == {"old", "run-2"}


def test_anger_and_mood_are_sealed(cfg):
    from aurora import kno_anger, kno_mood
    kno_anger._save(cfg, [{"at": time.time(), "words": SECRET}])
    assert _clean(kno_anger._file(cfg)) and kno_anger._events(cfg)[0]["words"] == SECRET
    kno_anger._file(cfg).write_text(json.dumps([{"at": 1.0, "words": "di prima"}]))
    assert kno_anger._events(cfg)[0]["words"] == "di prima"
    cfg.values["AURORA_MOOD"] = True
    m = {"on": True, "at": time.time(), "dominant": "worry", "emotions": {"worry": {"value": 0.7, "causes": [SECRET]}}}
    kno_mood.save(cfg, m)
    f = kno_mood._last_file(cfg)
    assert _clean(f) and kno_mood.last(cfg) == m
    from conftest import private
    assert private(f)
    f.write_text(json.dumps({**m, "emotions": {"worry": {"value": 0.7, "causes": ["di prima"]}}}))
    assert kno_mood.last(cfg)["emotions"]["worry"]["causes"] == ["di prima"]


def test_the_learnt_private_values_are_sealed(cfg):
    from aurora import sec_mask_spot as S
    S._learn(cfg, [SECRET, "Borgo Inventato"])
    f = S._file(cfg)
    assert _clean(f) and b"Borgo" not in f.read_bytes()
    assert set(S.learned(cfg)) == {SECRET, "Borgo Inventato"}
    assert S.forget(cfg, "Borgo Inventato") and S.learned(cfg) == [SECRET] and _clean(f)
    f.write_text(json.dumps({"words": ["Valle Finta"], "at": 1.0}))         # a file of before
    assert S.learned(cfg) == ["Valle Finta"]


def test_approvals_are_sealed(cfg):
    from aurora.sys_approvals import Approvals
    a = Approvals(cfg)
    item = a.request("tool_call", "external", "email.send", f"scrivere a {SECRET}", {"to": SECRET},
                     {"plugin": "email", "tool": "send", "args": {"body": SECRET}})
    assert _clean(a.file) and a.get(item["id"])["preview"] == {"to": SECRET}
    a.update(item["id"], status="executed", result=SECRET)
    assert _clean(a.file) and a.list("executed")[0]["result"] == SECRET
    a.file.write_text(json.dumps([{**item, "id": "old1", "purpose": "di prima"}]))
    assert a.get("old1")["purpose"] == "di prima"


def test_plugin_results_are_sealed(cfg):
    from aurora import plg_shadow
    plg_shadow.put(cfg, "weather", "forecast", {"place": "Borgo"}, SECRET)
    assert plg_shadow.get(cfg, "weather", "forecast", {"place": "Borgo"}, 60) == SECRET
    with closing(plg_shadow._db(cfg, "weather")) as con:
        (k, text) = con.execute("SELECT key, text FROM shadow").fetchone()
    assert sys_seal.is_sealed(text) and SECRET not in text
    import hashlib
    plain = hashlib.sha256(json.dumps(["forecast", {"place": "Borgo"}], sort_keys=True).encode()).hexdigest()
    assert k != plain                                       # a guessed argument is not confirmed from the file


def test_the_plain_hash_cache_of_before_is_dropped(cfg):
    from aurora import plg_shadow, sys_users_layout
    d = sys_users_layout.place(cfg, "state", cfg.user) / "plugin_shadow"
    d.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(d / "weather.db")) as con, con:
        con.execute("CREATE TABLE results (key TEXT PRIMARY KEY, tool TEXT, text TEXT, at REAL, used INTEGER DEFAULT 0)")
        con.execute("INSERT INTO results VALUES ('abc', 'forecast', 'di prima', ?, 0)", (time.time(),))
    assert plg_shadow.stats(cfg)["weather"] == {"results": 0, "served": 0}
    with closing(sqlite3.connect(d / "weather.db")) as con:
        assert con.execute("SELECT name FROM sqlite_schema WHERE name = 'results'").fetchone() is None


def test_a_projects_talk_and_its_mask_map_are_sealed(cfg, monkeypatch):
    from aurora import prj_conduct, prj_talk
    monkeypatch.setattr(prj_conduct, "_project", lambda cfg, name: None)
    prj_talk._add(cfg, "orsa", "owner", SECRET)
    prj_talk._keep_session(cfg, "orsa", {"session": "s1", "mask": {"[PERSON_1]": SECRET}})
    d = prj_talk._dir(cfg, "orsa")
    assert _clean(d / "talk.jsonl") and _clean(d / "talk.json")
    assert prj_talk.turns(cfg, "orsa")[0]["text"] == SECRET
    assert prj_talk.session(cfg, "orsa")["mask"] == {"[PERSON_1]": SECRET}
    with (d / "talk.jsonl").open("a") as fh:                                 # a line of before beside the sealed one
        fh.write(json.dumps({"id": "x", "t": 1.0, "role": "conductor", "text": "di prima"}) + "\n")
    assert [t["text"] for t in prj_talk.turns(cfg, "orsa")] == [SECRET, "di prima"]
    (d / "talk.json").write_text(json.dumps({"session": "old"}))
    assert prj_talk.session(cfg, "orsa") == {"session": "old"}


def test_push_history_is_sealed_and_the_phone_gets_a_neutral_body(cfg):
    msg = {"title": "💭 Un pensiero di Aurora", "body": SECRET, "view": "diary"}
    REMEMBER(msg, "rem.thought", ["push"], cfg)
    f = sys_push._mine(cfg) / "history.jsonl"
    assert _clean(f)
    h = sys_push.history(cfg)
    assert h[0]["body"] == SECRET and h[0]["title"] == msg["title"]
    with f.open("a") as fh:                                                  # a line of before
        fh.write(json.dumps({"at": 1.0, "event": "rem.dream", "title": "t", "body": "di prima"}) + "\n")
    assert [e["body"] for e in sys_push.history(cfg)] == ["di prima", SECRET]
    assert cfg["AURORA_PUSH_PRIVATE"] is True                                # recommended
    out = sys_push.outgoing(msg, cfg)
    assert out["body"] == "Aurora ha qualcosa per te" and out["title"] == msg["title"]
    cfg.values["AURORA_LANG_DEFAULT"] = "en_US"
    assert sys_push.outgoing(msg, cfg)["body"] == "Aurora has something for you"
    cfg.values["AURORA_PUSH_PRIVATE"] = False
    assert sys_push.outgoing(msg, cfg)["body"] == SECRET


def test_the_push_sent_carries_the_neutral_body(cfg, monkeypatch):
    import pywebpush
    sent = []
    sys_push.subscribe({"endpoint": "https://push.example/abc", "keys": {"p256dh": "k", "auth": "a"}}, None, cfg)
    monkeypatch.setattr(pywebpush, "webpush", lambda info, data, **kw: sent.append(json.loads(data)))
    SEND({"title": "🔁 Routine di Aurora", "body": SECRET, "view": "routines", "tag": "t"}, cfg)
    assert sent and sent[0]["body"] == "Aurora ha qualcosa per te" and SECRET not in json.dumps(sent)


def test_tts_clips_are_sealed_and_named_by_a_keyed_hash(cfg):
    import hashlib
    from aurora import mdl_tts
    what = f"paola\n1 0 0 0\n{SECRET}"
    f = mdl_tts._clip(cfg, what)
    assert hashlib.sha256(what.encode()).hexdigest()[:32] not in f.name     # the text alone does not name it
    mdl_tts._keep(cfg, f, b"RIFF" + SECRET.encode())
    assert _clean(f) and mdl_tts._cached(cfg, f) == b"RIFF" + SECRET.encode()
    assert mdl_tts._clip(cfg, what) == f                                     # the same salt next time
    old = mdl_tts._cache_dir(cfg) / "old.wav"
    old.write_bytes(b"RIFF di prima")
    assert mdl_tts._cached(cfg, old) == b"RIFF di prima"


def test_uploads_and_their_index_are_sealed_and_open_for_their_owner(cfg):
    from aurora import doc_artifact, sys_uploads
    item = sys_uploads.save(cfg, "run-1", f"{SECRET}.txt", "text/plain", SECRET.encode())
    found = sys_uploads.get(cfg, item["id"])
    assert SECRET.encode() not in open(found[0], "rb").read()                # the bytes on disk
    assert b"Zanzibar" not in (sys_uploads._dir(cfg) / "index.json").read_bytes()
    assert sys_uploads.read(cfg, item["id"])[0] == SECRET.encode()
    assert found[0].read_bytes() == SECRET.encode()                          # a reader of before, through get()'s path
    copy = sys_uploads.plain_copy(cfg, item["id"])
    assert copy.read_bytes() == SECRET.encode() and sys_uploads._dir(cfg) not in copy.parents
    assert sys_uploads.all_uploads(cfg)[0]["name"] == f"{SECRET}.txt"
    pic = sys_uploads.save(cfg, "run-1", "dipinto.png", "image/png", b"\x89PNG plain", role="assistant")
    assert open(sys_uploads.get(cfg, pic["id"])[0], "rb").read() == b"\x89PNG plain"   # the social plugins post it
    page = sys_uploads.save(cfg, "run-1", "pagina.html", "text/html", f"<p>{SECRET}</p>".encode(), role="assistant")
    tok = doc_artifact.open_token(cfg, f"/v1/aurora/uploads/{page['id']}")
    assert doc_artifact.page(tok) == f"<p>{SECRET}</p>".encode()
    # an index and a file of before
    rel = "2026-09/aaaaaaaaaaaaaaaa-old.txt"
    (sys_uploads._dir(cfg) / rel).parent.mkdir(parents=True)
    (sys_uploads._dir(cfg) / rel).write_bytes(b"di prima")
    (sys_uploads._dir(cfg) / "index.json").write_text(json.dumps([{"id": "aaaaaaaaaaaaaaaa", "name": "old.txt",
        "mime": "text/plain", "size": 8, "run_id": "r0", "created": 1.0, "path": rel, "role": "user"}]))
    assert sys_uploads.read(cfg, "aaaaaaaaaaaaaaaa")[0] == b"di prima"
    assert sys_uploads.plain_copy(cfg, "aaaaaaaaaaaaaaaa") == (sys_uploads._dir(cfg) / rel).resolve()


def test_the_download_endpoint_opens_a_sealed_upload(cfg, monkeypatch):
    import importlib
    import sys
    from aurora import sys_config, sys_uploads
    monkeypatch.setattr(sys_config, "_cached", cfg)                          # the API imported with this test's config
    for m in [m for m in sys.modules if m.startswith("aurora.api")]:
        monkeypatch.delitem(sys.modules, m)
    for name in ("oai", "runs"):                                             # the app's own order (svc_api)
        importlib.import_module(f"aurora.api.{name}")
    api = importlib.import_module("aurora.api.uploads")
    monkeypatch.setattr(api, "cfg", cfg)
    item = sys_uploads.save(cfg, "run-1", "nota.txt", "text/plain", SECRET.encode())
    r = api.upload_get(item["id"], type("Asked", (), {"headers": {}})())
    assert r.body == SECRET.encode() and "attachment" in r.headers["content-disposition"]
    assert r.headers["content-security-policy"] == "sandbox"


VEC = {"Domanda inventata?": [1, 0, 0], "Domanda inventata, quasi?": [0.99, 0.14, 0]}


class Emb:
    def encode_queries(self, texts):
        return [VEC[t] for t in texts]


class RR:
    def score(self, pairs):
        return [0.99 for _ in pairs]


def test_the_shadow_rows_are_sealed_and_still_found(cfg):
    from aurora import kno_shadow as K
    cfg.values.update(AURORA_SHADOW_COS=0.9, AURORA_SHADOW_ANSWER=0.5, AURORA_SHADOW_SURE=0.97)
    K.add(cfg, Emb(), "Domanda inventata?", f"{SECRET} [1]", [{"source": "arxiv:1", "n": 1, "title": SECRET}],
          follow=[SECRET])
    K.add(cfg, Emb(), "Domanda inventata?", f"{SECRET} di nuovo [1]", [{"source": "arxiv:1", "n": 1}])  # replaces it
    db = next(p for p in cfg.path("AURORA_STATUS_DIR").rglob("shadow.db"))
    assert _clean(db) and b"inventata" not in db.read_bytes()
    with closing(sqlite3.connect(db)) as con:
        rows = con.execute("SELECT question, vec FROM shadows").fetchall()
    assert len(rows) == 1 and all(sys_seal.is_sealed(v) for v in rows[0])
    hit = K.find(cfg, Emb(), RR(), "Domanda inventata, quasi?")
    assert hit["question"] == "Domanda inventata?" and hit["text"] == f"{SECRET} di nuovo [1]"
    assert hit["sources"][0]["source"] == "arxiv:1" and K.stats(cfg)["answers"] == 1
    with closing(sqlite3.connect(db)) as con, con:                           # a row of before, in plaintext
        con.execute("DELETE FROM shadows")
        con.execute("INSERT INTO shadows (question, vec, answer, sources, made, last, origin, follow) VALUES "
                    "(?, ?, ?, ?, ?, ?, 'seed', ?)", ("Domanda inventata?", np.asarray([1, 0, 0], np.float32).tobytes(),
                                                      "di prima [1]", json.dumps([{"source": "arxiv:2", "n": 1}]), 1.0, 1.0, None))
    assert K.find(cfg, Emb(), RR(), "Domanda inventata, quasi?")["text"] == "di prima [1]"
    assert [r["answer"] for r in K.export_seed(cfg)] == ["di prima [1]"]
    assert K.import_seed(cfg, Emb(), [{"question": "Domanda inventata?", "answer": "x",
                                       "sources": [{"source": "arxiv:3"}]}]) == {"added": 0, "skipped": 1}


def test_the_admins_seed_serves_another_user_with_the_admins_key(cfg):
    """Multi-user: the admin's seed rows are sealed with the admin's key and still serve a guest (opened by Aurora,
    as they were read before); the guest's own shadow is sealed with the guest's key."""
    from aurora import kno_shadow as K, sys_config, sys_user_config as U, sys_users_layout as L
    from aurora.sys_users import Users
    users = Users(cfg)
    users.add("boss", "admin", "a long password")
    users.add("guest", "user")
    L.migrate(cfg, "boss")
    base = sys_config.load(cfg.env_file, check_root=False)
    base.values.update(AURORA_SHADOW_COS=0.9, AURORA_SHADOW_ANSWER=0.5, AURORA_SHADOW_SURE=0.97)
    boss, guest = U.for_user(base, "boss"), U.for_user(base, "guest")
    K.add(boss, Emb(), "Domanda inventata?", f"{SECRET} [1]", [{"source": "arxiv:1", "n": 1}], origin="seed")
    hit = K.find(guest, Emb(), RR(), "Domanda inventata, quasi?")
    assert hit and hit["text"] == f"{SECRET} [1]"
    assert _clean(L.place(base, "state", "boss") / "shadow.db")
    K.add(guest, Emb(), "Domanda inventata, quasi?", "della guest [1]", [{"source": "arxiv:9", "n": 1}])
    gdb = L.place(base, "state", "guest") / "shadow.db"
    assert b"guest [1]" not in gdb.read_bytes()
    with closing(sqlite3.connect(gdb)) as con:
        rid, q = con.execute("SELECT id, question FROM shadows").fetchone()
    import pytest
    with pytest.raises(ValueError):                                          # the admin's key does not open it
        sys_seal.open_text(base, q, K._label(rid, "question"), "boss")


def test_a_sealed_video_is_served_by_ranges_as_a_plain_file_is(cfg, monkeypatch):
    import importlib
    import sys
    import pytest
    from fastapi import HTTPException
    from aurora import sys_config, sys_uploads
    monkeypatch.setattr(sys_config, "_cached", cfg)                                 # the API's own cfg: this one
    for m in [m for m in sys.modules if m.startswith("aurora.api")]:
        monkeypatch.delitem(sys.modules, m)
    for name in ("oai", "runs"):                                                     # the app's own order (svc_api)
        importlib.import_module(f"aurora.api.{name}")
    from aurora.api import uploads
    data = bytes(range(256)) * 40
    item = sys_uploads.save(cfg, "run-1", "gita.mp4", "video/mp4", data)
    assert sys_seal.is_sealed(open(sys_uploads.get(cfg, item["id"])[0], "rb").read())

    class Asked:                                                                     # a player's request
        def __init__(self, rng): self.headers = {"range": rng} if rng else {}
    whole = uploads.upload_get(item["id"], Asked(""))
    assert whole.status_code == 200 and whole.body == data and whole.headers["accept-ranges"] == "bytes"
    part = uploads.upload_get(item["id"], Asked("bytes=100-199"))
    assert part.status_code == 206 and part.body == data[100:200]
    assert part.headers["content-range"] == f"bytes 100-199/{len(data)}"
    assert uploads.upload_get(item["id"], Asked("bytes=-10")).body == data[-10:]
    assert uploads.upload_get(item["id"], Asked("bytes=10000-")).body == data[10000:]
    with pytest.raises(HTTPException) as e:
        uploads.upload_get(item["id"], Asked(f"bytes={len(data)}-"))
    assert e.value.status_code == 416


def test_a_picture_a_user_asked_for_is_sealed_and_aurora_s_own_is_not(cfg):
    from aurora import sys_uploads
    asked = sys_uploads.save(cfg, "run-2", "aurora-1.png", "image/png", b"\x89PNG " + SECRET.encode(), role="assistant",
                             private=True)
    on_disk = open(sys_uploads.get(cfg, asked["id"])[0], "rb").read()
    assert sys_seal.is_sealed(on_disk) and SECRET.encode() not in on_disk
    assert sys_uploads.read(cfg, asked["id"])[0] == b"\x89PNG " + SECRET.encode()
    own = sys_uploads.save(cfg, "run-2", "dream.png", "image/png", b"\x89PNG own", role="assistant")
    assert open(sys_uploads.get(cfg, own["id"])[0], "rb").read() == b"\x89PNG own"      # the social plugins post it
