# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Run by test_c595_accounts.py in its own process (the API keeps state in its modules): a fake installation with
`boss` (the admin) and `guest`, three failed logins before an address is refused. argv: the root. Prints one JSON line
of results. Made-up users."""
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

PW = {"boss": "the boss's long password", "guest": "the guest's long password"}
users = Users(base)
for n, role in (("boss", "admin"), ("guest", "user")):
    users.add(n, role, PW[n])
    L.make_home(base, n)
C._cached = C._view(base)

import svc_api  # noqa: E402
from aurora import sec_hostfw, sys_autonomy, sys_users_perm  # noqa: E402
from aurora.api import core  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

sec_hostfw.block = lambda *a, **k: {"ok": False}        # a lockout here never reaches this machine's firewall
client = lambda **k: TestClient(svc_api.app, base_url="https://testserver", **k)       # noqa: E731
tok = {n: core.devices.register(f"{n} phone", "ua", user=n) for n in ("boss", "guest")}
H = {n: {"Authorization": f"Bearer {t[0]}"} for n, t in tok.items()}
out = {}
c = client()

# A7: the «routines» permission holds for a set and for an advice too
sys_users_perm.set_(base, "guest", "routines", False)
out["apply_kept"] = [c.post("/v1/aurora/routines/templates/social/apply", headers=H["guest"]).status_code,
                     c.post("/v1/aurora/routines/advice/x/apply", headers=H["guest"]).status_code]
sys_users_perm.set_(base, "guest", "routines", True)
out["apply_allowed"] = [c.post("/v1/aurora/routines/templates/no-such-set/apply", headers=H["guest"]).status_code,
                        c.post("/v1/aurora/routines/advice/x/apply", headers=H["guest"]).status_code]

# A6: a user's autonomy through the settings, only when the admin lets them choose it
put = lambda who, body: c.put("/v1/aurora/settings", json=body, headers=H[who]).status_code      # noqa: E731
out["autonomy_kept"] = put("guest", {"AURORA_HA_COMMANDS": "2"})
sys_autonomy.set_may_choose(base, "guest", True)
out["autonomy_allowed"] = put("guest", {"AURORA_HA_COMMANDS": "2"})

# A3: the telescope's PC of a user is never an address of the house or of this machine
out["astro_pc"] = [put("guest", {"AURORA_ASTRO_PC": v}) for v in ("127.0.0.1:22", "192.168.1.9", "localhost:9700", "8.8.8.8")]
out["astro_pc_admin"] = put("boss", {"AURORA_ASTRO_PC": "192.168.1.9"})
out["astro_pc_same_as_admin"] = put("guest", {"AURORA_ASTRO_PC": "192.168.1.9"})

# A9: the machine's folders and the services' details are the admin's
out["factory"] = [c.get("/v1/aurora/factory", headers=H[n]).status_code for n in ("guest", "boss")]
st = {n: c.get("/v1/aurora/status", headers=H[n]).json() for n in ("guest", "boss")}
out["status_guest_keys"] = sorted({k for v in st["guest"].values() if isinstance(v, dict) for k in v})
out["status_boss_has_more"] = any(set(v) - {"status"} for v in st["boss"].values() if isinstance(v, dict))

# A8: wrong logins counted per account: 3 an address, 12 for the name, each from another address
login = lambda ip, pw: client(client=("127.0.0.1", 40000)).post(                                   # noqa: E731
    "/v1/aurora/login", json={"name": "guest", "password": pw}, headers={"X-Forwarded-For": ip}).status_code
out["guesses"] = sorted({login(f"198.51.100.{i}", "a wrong password") for i in range(12)})
out["thirteenth_elsewhere"] = login("198.51.100.200", "a wrong password")
out["right_password_from_outside"] = login("198.51.100.201", PW["guest"])
out["right_password_at_home"] = login("192.168.1.50", PW["guest"])
print(json.dumps(out))
