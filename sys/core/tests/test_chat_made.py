# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The documents a routine wrote are said in the chat (api/knowledge.made_lately): only the recent runs that made some."""
import time
from datetime import datetime, timedelta, timezone


def test_a_routine_s_new_documents_come_to_the_chat(cfg, monkeypatch):
    import importlib
    import sys
    from aurora import sys_config, sys_routines
    monkeypatch.setattr(sys_config, "_cached", cfg)                                 # the API's own cfg: this one
    for m in [m for m in sys.modules if m.startswith("aurora.api")]:
        monkeypatch.delitem(sys.modules, m)
    for name in ("oai", "runs"):                                                     # the app's own order (svc_api)
        importlib.import_module(f"aurora.api.{name}")
    from aurora.api import knowledge
    docs = cfg.path("AURORA_DOCUMENTS_DIR")
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "readme.pdf").write_bytes(b"%PDF-1.4")                                    # still there: not «in the trash»
    now = time.time()
    monkeypatch.setattr(sys_routines, "all_routines", lambda cfg: [
        {"id": "a1", "title": "Documentazione progetti", "last_run": now - 3600,
         "last_files": [{"name": "readme.pdf", "url": "/v1/aurora/documents/readme.pdf", "mime": "application/pdf"}]},
        {"id": "b2", "title": "Meteo", "last_run": now - 600, "last_files": []},                       # nothing made
        {"id": "c3", "title": "Vecchia", "last_run": now - 5 * 86400, "last_files": [{"name": "x.pdf", "url": "/x"}]}])
    out = knowledge.made_lately(datetime.now(timezone.utc) - timedelta(hours=24))
    assert [x["routine"] for x in out] == ["Documentazione progetti"] and out[0]["role"] == "made"
    assert out[0]["files"][0]["name"] == "readme.pdf" and datetime.fromisoformat(out[0]["created_at"]).tzinfo
    (docs / "readme.pdf").unlink()                                                    # moved to the trash from the chat
    assert knowledge.made_lately(datetime.now(timezone.utc) - timedelta(hours=24))[0]["files"][0]["trashed"]
