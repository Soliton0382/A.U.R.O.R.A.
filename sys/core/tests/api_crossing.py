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
r = client.post("/v1/aurora/calendar/items", headers=H["boss"], json={"title": SECRET, "start": "2030-01-10T10:00"})
assert r.status_code == 200, r.text
cal_id = r.json()["item"]["id"]
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
    seen["calendar"] = SECRET in get(who, "/v1/aurora/calendar?start=2030-01-08&end=2030-01-15").text
    seen["calendar_export"] = SECRET in get(who, "/v1/aurora/calendar/export.ics").text
    seen["calendar_item"] = get(who, f"/v1/aurora/calendar/items/{cal_id}").status_code
    seen["devices"] = sorted(d["name"] for d in get(who, "/v1/aurora/devices").json())
    seen["users_page"] = get(who, "/v1/aurora/users").status_code
    seen["machine_setting"] = client.put("/v1/aurora/settings", headers=H[who], json={"AURORA_LOG_MAX_MB": "50"}).status_code
    mine = get(who, "/v1/aurora/settings").json()["settings"]                     # ⚙️ for everyone: a user's own only
    seen["only_own_settings"] = all(s.get("scope") == "user" for s in mine)
    if who == "guest":
        core._state.setdefault("pipelines", {})["guest"] = object()               # their answers' configuration, made
        seen["own_setting"] = client.put("/v1/aurora/settings", headers=H[who],
                                         json={"AURORA_WEATHER_LAT": "45.5"}).status_code
        seen["own_setting_read"] = next(s["value"] for s in get(who, "/v1/aurora/settings").json()["settings"]
                                        if s["key"] == "AURORA_WEATHER_LAT")
        seen["pipeline_dropped"] = "guest" not in core._state["pipelines"]
    seen["logs"] = client.get("/v1/aurora/logs", headers=H[who]).status_code             # C414
    seen["forge"] = client.get("/v1/aurora/forge", headers=H[who]).status_code                       # C422
    if who == "guest":                                  # refused before anything runs; the admin's would use the machine's
        seen["photo"] = client.post("/v1/aurora/senses/photo", headers=H[who], json={}).status_code    # camera (C421)
        seen["senses_devices"] = client.get("/v1/aurora/senses/devices", headers=H[who]).status_code
        seen["forge_tick"] = client.post("/v1/aurora/forge/tick", headers=H[who], json={}).status_code
    if who == "guest":                                  # a services' line; a machine approval in the user's own list
        seen["activity_post"] = client.post("/v1/aurora/activity", headers=H[who],
                                       json={"event": "security.honeypot", "payload": {"site": "x"}}).status_code
        with sys_context.acting_as("guest"):
            aid = Approvals(C.get()).request("plugin_install", "code_change", "a plugin", "for everyone", {}, {})["id"]
        seen["approve_plugin"] = client.post(f"/v1/aurora/approvals/{aid}/approve", headers=H[who]).status_code
    seen["log_tail"] = client.get("/v1/aurora/logs/api", headers=H[who]).status_code
    seen["ups"] = client.get("/v1/aurora/ups", headers=H[who]).status_code               # C416
    if who == "guest":                                  # the admin's would move Caddy, file an incident: only refused
        seen["ports"] = client.put("/v1/aurora/settings", headers=H[who], json={"AURORA_HTTPS_PORT": "8443"}).status_code
        seen["incident"] = client.post("/v1/aurora/sentinel/incident", headers=H[who],
                                       json={"source": "10.0.0.9", "kind": "made up"}).status_code
    out[who] = seen
boss_dev = next(d["id"] for d in get("boss", "/v1/aurora/devices").json() if d["name"] == "boss phone")
out["guest"]["revoke_boss_device"] = client.delete(f"/v1/aurora/devices/{boss_dev}", headers=H["guest"]).status_code
# cloud accounts (106): boss's own key never reaches guest; the shared ones and the policy are the admin's
acc = client.post("/v1/aurora/accounts", headers=H["boss"], json={"provider": "openai", "scope": "user", "key": "sk-" + SECRET}).json()
out["guest"]["accounts_list"] = SECRET[-4:] in get("guest", "/v1/aurora/accounts").text or acc["id"] in get("guest", "/v1/aurora/accounts").text
out["guest"]["account_remove"] = client.delete(f"/v1/aurora/accounts/{acc['id']}", headers=H["guest"]).status_code
out["guest"]["account_shared"] = client.post("/v1/aurora/accounts", headers=H["guest"], json={"provider": "openai", "scope": "shared", "key": "sk-guest-123456"}).status_code
out["guest"]["account_policy"] = client.put("/v1/aurora/accounts/policy", headers=H["guest"], json={"policy": "own"}).status_code
out["guest"]["service_add"] = client.post("/v1/aurora/accounts/services", headers=H["guest"], json={"name": "x", "base": "http://localhost:1/v1"}).status_code
out["boss"]["accounts_list"] = acc["id"] in get("boss", "/v1/aurora/accounts").text
# the first run (107): seen once per person
client.post("/v1/aurora/me/welcomed", headers=H["boss"])
out["boss"]["welcomed"] = get("boss", "/v1/aurora/me").json()["welcomed"]
out["guest"]["welcomed"] = get("guest", "/v1/aurora/me").json()["welcomed"]
# the menu's style and pins (107): each person's, on any device
client.put("/v1/aurora/me/prefs", headers=H["boss"], json={"style": "essenziale", "theme": "foresta", "pins": ["dreams", "models"]})
out["boss"]["prefs"] = get("boss", "/v1/aurora/me").json()["prefs"]
out["guest"]["prefs"] = get("guest", "/v1/aurora/me").json()["prefs"]
out["guest"]["prefs_bad"] = client.put("/v1/aurora/me/prefs", headers=H["guest"], json={"style": "<script>"}).status_code
# a social account connected from the card (api/oauth): the admin's, with a state Aurora gave, once
import httpx as _httpx  # noqa: E402
out["guest"]["oauth_start"] = client.post("/v1/aurora/oauth/tiktok/start", headers=H["guest"]).status_code
out["boss"]["oauth_no_keys"] = client.post("/v1/aurora/oauth/tiktok/start", headers=H["boss"]).status_code
client.put("/v1/aurora/settings", headers=H["boss"], json={"AURORA_TIKTOK_CLIENT_KEY": "ck123", "AURORA_TIKTOK_CLIENT_SECRET": "cs456",
                                                          "AURORA_TIKTOK_REDIRECT_URI": "https://aurora.example.org/"})
url = client.post("/v1/aurora/oauth/tiktok/start", headers=H["boss"]).json()["url"]
import urllib.parse as _up  # noqa: E402
q = dict(_up.parse_qsl(_up.urlparse(url).query))
out["boss"]["oauth_scope"] = q["scope"]
out["boss"]["oauth_forged"] = client.post("/v1/aurora/oauth/finish", headers=H["boss"], json={"code": "c", "state": "tiktok.forged"}).status_code
out["guest"]["oauth_finish"] = client.post("/v1/aurora/oauth/finish", headers=H["guest"], json={"code": "c", "state": q["state"]}).status_code
_real = _httpx.post
_httpx.post = lambda u, timeout, data: type("R", (), {"json": lambda self: {"refresh_token": "rt-" + data["code"], "scope": "user.info.basic,video.publish", "refresh_expires_in": 31536000}})()
out["boss"]["oauth_finish"] = client.post("/v1/aurora/oauth/finish", headers=H["boss"], json={"code": "good", "state": q["state"]}).json()
out["boss"]["oauth_again"] = client.post("/v1/aurora/oauth/finish", headers=H["boss"], json={"code": "good", "state": q["state"]}).status_code
_httpx.post = _real
from aurora import sys_user_config as _uc  # noqa: E402
out["boss"]["oauth_saved"] = "AURORA_TIKTOK_REFRESH_TOKEN=rt-good" in _uc.env_path(base, "boss").read_text()
out["guest"]["oauth_saved"] = _uc.env_path(base, "guest").exists() and "rt-good" in _uc.env_path(base, "guest").read_text()
out["guest"]["oauth_machine"] = "rt-good" in (root / ".env").read_text()
out["guest"]["theme_bad"] = client.put("/v1/aurora/me/prefs", headers=H["guest"], json={"theme": "x;}body{"}).status_code
# Oggi's tiles (19 Oct): each person's order and hidden ones; an id that is not a word refused
out["guest"]["tiles"] = client.put("/v1/aurora/me/prefs", headers=H["guest"],
                                   json={"tiles": {"order": ["sky", "agenda", "sky", "page:ideas"], "off": ["news"]}}).json().get("tiles")
out["guest"]["tiles_bad"] = client.put("/v1/aurora/me/prefs", headers=H["guest"], json={"tiles": {"order": ["<b>"]}}).status_code
# a user's cloud ceiling: the admin's to set, never the user's own, never the admin's (17 Oct)
out["guest"]["cloud_set"] = client.put("/v1/aurora/users/cloud", headers=H["guest"], json={"user": "guest", "tokens": 10**9}).status_code
out["boss"]["cloud_set"] = client.put("/v1/aurora/users/cloud", headers=H["boss"], json={"user": "guest", "tokens": 200000}).json()["cloud"]
out["boss"]["cloud_self"] = client.put("/v1/aurora/users/cloud", headers=H["boss"], json={"user": "boss", "tokens": 5}).status_code
out["boss"]["cloud_list"] = {u["name"]: u["cloud_cap"] for u in get("boss", "/v1/aurora/users").json()["users"]}
# the machine's health: the admin sees its items, a user only its level (17 Oct)
import time as _t  # noqa: E402
from aurora.api import activity as _act  # noqa: E402
_act._health_cache.update(at=_t.time(), value={"level": "warn", "items": [{"name": "backup", "text": "/mnt/x"}],
                                               "problems": ["backup"], "checked": "now"})
for who in ("boss", "guest"):
    h = get(who, "/v1/aurora/health").json()
    out[who]["health"] = [h["level"], len(h["items"]), len(h["problems"])]
# the usage page: the admin sees everyone and may pick one; a user only their own, whatever they ask (17 Oct)
from aurora import sys_log as _log  # noqa: E402
for who in ("boss", "guest", None):
    with sys_context.acting_as(who):
        _log.trace("plugins", "plugin.call", {"plugin": "p", "tool": "t", "ok": True, "seconds": 0.1})
for who in ("boss", "guest"):
    u = get(who, "/v1/aurora/usage?days=1").json()
    out[who]["usage"] = [u["everyone"], u["names"], u["totals"]["tool_calls"]]
    out[who]["usage_pick"] = get(who, "/v1/aurora/usage?days=1&user=boss").json()["totals"]["tool_calls"]
# C457: the machine's logs in a bug report, a plugin's icon everyone sees, another user's saved set of routines
out["guest"]["bugreport"] = client.post("/v1/aurora/bugreport", headers=H["guest"], json={"description": "x"}).status_code
out["guest"]["plugin_icon"] = client.post("/v1/aurora/plugins/calendar/icon", headers=H["guest"], json={"data": ""}).status_code
from aurora import sys_routine_templates as _rt  # noqa: E402
_tpl = _rt._dir(C.get()); _tpl.mkdir(parents=True, exist_ok=True)
(_tpl / "mine-serata.json").write_text(json.dumps({"id": "mine-serata", "saved_by": "boss", "routines": []}))
with sys_context.acting_as("guest"):
    try:
        _rt.save_mine(C.get(), "Serata", "guest")
        out["guest"]["template_over"] = "saved"
    except ValueError as e:
        out["guest"]["template_over"] = "refused" if "someone else" in str(e) else str(e)
out["guest"]["template_kept"] = json.loads((_tpl / "mine-serata.json").read_text())["saved_by"]
print(json.dumps(out))
