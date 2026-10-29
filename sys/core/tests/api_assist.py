# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Run by test_assist.py in its own process (the API keeps state in its modules): a fake installation with `boss`
(the admin) and `guest`; guest opens the assistance, boss enters, works as guest, is refused the account's keys,
leaves; guest's log and notifications. Prints one JSON line of results."""
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
from aurora import sys_assist  # noqa: E402
from aurora.api import core  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

tok = {n: core.devices.register(f"{n} phone", "ua", user=n)[0] for n in ("boss", "guest")}
client = TestClient(svc_api.app)
H = {n: {"Authorization": f"Bearer {t}"} for n, t in tok.items()}
K = {"Authorization": f"Bearer {base['AURORA_API_KEY']}"}
out = {}
me = lambda h: client.get("/v1/aurora/me", headers=h).json()             # noqa: E731
out["enter_closed"] = client.post("/v1/aurora/assist/enter", headers=H["boss"], json={"user": "guest"}).status_code
out["grant_bad"] = client.post("/v1/aurora/assist/grant", headers=H["guest"], json={"hours": 5}).status_code
out["grant_admin"] = client.post("/v1/aurora/assist/grant", headers=H["boss"], json={"hours": 8}).status_code
out["grant"] = client.post("/v1/aurora/assist/grant", headers=H["guest"], json={"hours": 8}).status_code
out["listed"] = bool(next(u for u in client.get("/v1/aurora/users", headers=H["boss"]).json()["users"] if u["name"] == "guest")["assist"])
out["guest_enters"] = client.post("/v1/aurora/assist/enter", headers=H["guest"], json={"user": "guest"}).status_code
out["key_enters"] = client.post("/v1/aurora/assist/enter", headers=K, json={"user": "guest"}).status_code
out["enter"] = client.post("/v1/aurora/assist/enter", headers=H["boss"], json={"user": "guest"}).status_code
m = me(H["boss"])
out["inside_me"] = [m["name"], m["admin"], (m["assist"] or {}).get("by")]
out["inside_key"] = me(K)["name"]                                             # the API key stays the admin's
out["inside_users_page"] = client.get("/v1/aurora/users", headers=H["boss"]).status_code
out["refused"] = {p: client.request(meth, p, headers=H["boss"], json={}).status_code for meth, p in (
    ("POST", "/v1/aurora/me/password"), ("POST", "/v1/aurora/me/totp"), ("GET", "/v1/aurora/me/keys"),
    ("GET", "/v1/aurora/devices"), ("POST", "/v1/aurora/logout"), ("POST", "/v1/aurora/assist/grant"),
    ("POST", "/v1/aurora/assist/revoke"))}
out["guest_sees_inside"] = client.get("/v1/aurora/assist", headers=H["guest"]).json()["inside"]
out["leave"] = client.post("/v1/aurora/assist/leave", headers=H["boss"], json={}).json()
out["after_me"] = me(H["boss"])["name"]
client.post("/v1/aurora/assist/enter", headers=H["boss"], json={"user": "guest"})
out["revoke"] = client.post("/v1/aurora/assist/revoke", headers=H["guest"], json={}).json()
out["after_revoke_me"] = me(H["boss"])["name"]
# a window ended by its time: the tick drops it and tells
sys_assist.grant(base, "guest", 8)
client.post("/v1/aurora/assist/enter", headers=H["boss"], json={"user": "guest"})
d = sys_assist._load(base)
d["grants"]["guest"]["until"] = 1.0
sys_assist._save(base, d)
out["expired_me"] = me(H["boss"])["name"]
from aurora.api import assist as A  # noqa: E402
A.expire_due()
out["expired_dropped"] = sys_assist._load(base) == {"grants": {}, "sessions": {}}
log = client.get("/v1/aurora/assist", headers=H["guest"]).json()["log"]
out["log"] = [s["what"] for s in log][::-1]
out["log_paths"] = [s["path"] for s in log if s["what"] == "GET"]
out["told"] = [i["event"] for i in core._activity if i["user"] == "guest" and i["event"].startswith("assist.")]
out["boss_told"] = [i["event"] for i in core._activity if i["user"] == "boss" and i["event"].startswith("assist.")]
print(json.dumps(out))
