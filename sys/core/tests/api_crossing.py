# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Run by test_users_crossing.py in its own process (the API keeps state in its modules): a fake installation with
two users, `boss` (the admin) and `guest`; boss writes private things of every kind, guest looks for them through
every route that lists or serves them. Prints one JSON line of results."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "script"))

from aurora import sys_config as C  # noqa: E402

root = Path(sys.argv[1])
base = C.load(root / ".env", check_root=False)
(base.path("AURORA_STATUS_DIR")).mkdir(parents=True, exist_ok=True)
(base.path("AURORA_STATUS_DIR") / "users_layout.json").write_text(json.dumps({"layout": 1, "admin": "boss"}))
from aurora.sys_users import Users  # noqa: E402
from aurora import sys_users_layout as L  # noqa: E402

users = Users(base)
users.add("boss", "admin", "a long password")
users.add("guest", "user", "another long password")
for n in ("boss", "guest"):
    L.make_home(base, n)
C._cached = C._view(base)

import svc_api  # noqa: E402
from aurora import sys_context, sys_uploads  # noqa: E402
from aurora.api import core  # noqa: E402
from aurora.sol_schema import Soliton  # noqa: E402
from aurora.sol_writer import VaultWriter  # noqa: E402
from aurora.sys_approvals import Approvals  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

tok = {n: core.devices.register(f"{n} phone", "ua", user=n)[0] for n in ("boss", "guest")}
client = TestClient(svc_api.app)
H = {n: {"Authorization": f"Bearer {t}"} for n, t in tok.items()}
SECRET = "segreto di boss"
FILLER = " The measurement was repeated several times under controlled laboratory conditions." * 4

# boss's private things, through the API where it can, else as boss's work
r = client.post("/v1/aurora/activity", headers=H["boss"], json={"source": "t", "event": "boss.note", "payload": {"text": SECRET}})
assert r.status_code == 200, r.text
r = client.put("/v1/aurora/settings", headers=H["boss"], json={"AURORA_TMDB_TOKEN": "boss-tmdb-token"})
assert r.status_code == 200, r.text
r = client.post("/v1/aurora/routines", headers=H["boss"], json={"kind": "agent", "goal": SECRET, "title": SECRET,
                                                                   "schedule": {"every": "day", "at": "08:00"}})
assert r.status_code == 200, r.text
with sys_context.acting_as("boss"):
    ucfg = C.get()
    up = sys_uploads.public(sys_uploads.save(ucfg, "r1", "boss.png", "image/png", b"\x89PNG boss", role="user"))
    Approvals(ucfg).request("tool_call", "external", "x.y", SECRET, {}, {})
    VaultWriter(ucfg, user="boss").add_many([Soliton.new(SECRET + FILLER, "conversation", "conversation", "it", "run:r1",
                                                         extra={"role": "user", "run_id": "r1"})])
    (L.place(base, "documents", "boss") / "boss-secret.pdf").write_bytes(b"%PDF-1.4 boss")
    run = core.start_run(SECRET, "webui", job=lambda q, emit, rid: None)

out = {}


def get(who, path):
    return client.get(path, headers=H[who])


for who in ("boss", "guest"):
    seen = {}
    seen["me"] = get(who, "/v1/aurora/me").json()["name"]
    seen["activity"] = any(SECRET in json.dumps(a) for a in get(who, "/v1/aurora/activity").json())
    seen["settings_tmdb"] = next(s["value"] for s in get(who, "/v1/aurora/settings").json()["settings"]
                                 if s["key"] == "AURORA_TMDB_TOKEN") != ""
    seen["routines"] = SECRET in json.dumps(get(who, "/v1/aurora/routines").json())
    seen["uploads"] = len(get(who, "/v1/aurora/uploads").json()["files"])
    seen["upload_file"] = get(who, up["url"]).status_code
    seen["approvals"] = SECRET in json.dumps(get(who, "/v1/aurora/approvals").json())
    seen["history"] = SECRET in json.dumps(get(who, "/v1/aurora/history?n=20").json())
    seen["documents"] = "boss-secret.pdf" in json.dumps(get(who, "/v1/aurora/documents").json())
    seen["document_file"] = get(who, "/v1/aurora/documents/boss-secret.pdf").status_code
    seen["runs"] = any(x["id"] == run["id"] for x in get(who, "/v1/aurora/runs").json())
    seen["run_events"] = client.get(f"/v1/aurora/runs/{run['id']}/events", headers=H[who]).status_code
    seen["devices"] = sorted(d["name"] for d in get(who, "/v1/aurora/devices").json())
    seen["users_page"] = get(who, "/v1/aurora/users").status_code
    seen["machine_setting"] = client.put("/v1/aurora/settings", headers=H[who], json={"AURORA_LOG_MAX_MB": "50"}).status_code
    out[who] = seen
boss_dev = next(d["id"] for d in get("boss", "/v1/aurora/devices").json() if d["name"] == "boss phone")
out["guest"]["revoke_boss_device"] = client.delete(f"/v1/aurora/devices/{boss_dev}", headers=H["guest"]).status_code
print(json.dumps(out))
