# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The owner's list of 2026-10-04: plugins of the admin or of everyone, notifications nobody got, the trash,
routines with several times and groups of days, Aurora's code run in a cage of its own."""
import json
import shutil
import subprocess
import time
from datetime import date, datetime
from pathlib import Path

import pytest

from aurora import plg_access, prj_run, sys_log, sys_push, sys_routines as R, sys_trash, sys_uploads
from aurora.plg_host import PluginHost

from conftest import write_env


def _plugins(cfg, *names):
    for n in names:
        d = cfg.path("AURORA_PLUGINS_DIR") / n
        d.mkdir(parents=True)
        (d / "plugin.json").write_text(json.dumps({"name": n, "command": ["true"]}))


# ---- plugins: the admin's or everyone's ----------------------------------------------------------------------------
def test_the_machine_s_plugins_are_off_for_a_user_and_the_admin_shares_them(cfg):
    _plugins(cfg, "backup", "notes", "forged-thing")
    seen = {p.name: p.enabled for p in plg_access.UserPluginHost(cfg).plugins(with_tools=False)}
    assert seen == {"backup": False, "notes": True, "forged-thing": False}      # a new plugin: the admin's
    assert all(p.enabled for p in PluginHost(cfg).plugins(with_tools=False))   # the admin's host: unchanged
    plg_access.set_for_users(cfg, "forged-thing", True)
    plg_access.set_for_users(cfg, "notes", False)
    seen = {p.name: p.enabled for p in plg_access.UserPluginHost(cfg).plugins(with_tools=False)}
    assert seen == {"backup": False, "notes": False, "forged-thing": True}
    out = plg_access.UserPluginHost(cfg).call("backup", "status", {})
    assert out["ok"] is False and "not available" in out["text"]                # never called for the user


# ---- notifications ---------------------------------------------------------------------------------------------
def test_the_cloud_ceiling_and_a_stopped_plugin_can_be_notified(cfg):
    for ev in ("cloud.budget", "cloud.fallback", "plugin.refused"):
        assert ev in sys_push.TEXTS and sys_push.TEXTS[ev][0] in sys_push.KINDS
    assert "cloud" in sys_push.PRESETS["suggested"] and "cloud" in sys_push.MACHINE
    heard = []
    sys_log.on_trace(lambda c, e, p: heard.append(e))
    try:
        sys_log.trace("llm_client", "cloud.budget", {"provider": "xai", "spent": 600001, "cap": 600000})
    finally:
        sys_log._listeners.pop()
    assert heard == ["cloud.budget"]


def test_a_listener_that_fails_never_breaks_the_traced_work(cfg):
    sys_log.on_trace(lambda c, e, p: 1 / 0)
    try:
        assert sys_log.trace("t", "x", {}) > 0
    finally:
        sys_log._listeners.pop()


# ---- trash -------------------------------------------------------------------------------------------------------
def test_a_deleted_upload_goes_to_the_trash_and_comes_back(cfg):
    item = sys_uploads.save(cfg, "r1", "nota.txt", "text/plain", b"ciao")
    assert sys_uploads.delete(cfg, item["id"])
    assert sys_uploads.get(cfg, item["id"]) is None
    [t] = sys_trash.items(cfg)
    assert t["name"] == "nota.txt" and t["kind"] == "upload" and t["bytes"] == 4
    path, meta = sys_trash.restore(cfg, t["id"])
    sys_uploads.reindex(cfg, meta["record"], path)
    back = sys_uploads.get(cfg, item["id"])
    assert back and back[0].read_bytes() == b"ciao" and sys_trash.items(cfg) == []


def test_the_trash_expires_and_can_be_switched_off(cfg, tmp_path):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"%PDF")
    tid = sys_trash.discard(cfg, f, "document")
    assert not f.exists() and sys_trash.expire(cfg, now=time.time() + 29 * 86400) == 0
    assert sys_trash.expire(cfg, now=time.time() + 31 * 86400) == 1 and sys_trash.items(cfg) == []
    assert sys_trash.remove(cfg, tid) is False
    off = type(cfg).__new__(type(cfg))
    off.__dict__.update(cfg.__dict__)
    off.values = {**cfg.values, "AURORA_TRASH_ENABLED": False}
    g = tmp_path / "b.pdf"
    g.write_bytes(b"%PDF")
    assert sys_trash.discard(off, g, "document") is None and not g.exists()
    assert sys_trash._item(cfg, "../x") is None


# ---- routines --------------------------------------------------------------------------------------------------
def test_italian_holidays_and_easter():
    assert [R.easter(y) for y in (2025, 2026, 2027)] == [date(2025, 4, 20), date(2026, 4, 5), date(2027, 3, 28)]
    assert R.holiday_it(date(2026, 4, 6)) and R.holiday_it(date(2026, 6, 2)) and not R.holiday_it(date(2026, 6, 3))


def test_several_times_on_working_days():
    s = {"every": "custom", "times": ["08:00", "18:30"], "group": "workdays"}
    R.validate({"kind": "agent", "goal": "x", "schedule": s})
    at = lambda x: R._slot(datetime.fromisoformat(x), s)  # noqa: E731
    assert at("2026-10-05 07:00") == datetime(2026, 10, 2, 18, 30)       # Monday early: Friday evening's
    assert at("2026-10-05 09:00") == datetime(2026, 10, 5, 8, 0)
    assert at("2026-10-05 19:00") == datetime(2026, 10, 5, 18, 30)
    assert at("2026-12-08 12:00") == datetime(2026, 12, 7, 18, 30)       # a holiday is skipped
    r = {"enabled": True, "schedule": s, "created": datetime(2026, 10, 1).timestamp(),
         "last_run": datetime(2026, 10, 5, 8, 1).timestamp()}
    assert not R.is_due(r, datetime(2026, 10, 5, 12, 0)) and R.is_due(r, datetime(2026, 10, 5, 18, 31))


def test_chosen_days_and_bad_schedules():
    s = {"every": "custom", "times": ["07:15"], "days": [1, 3]}           # Tuesday and Thursday
    assert R._slot(datetime(2026, 10, 5, 9, 0), s) == datetime(2026, 10, 1, 7, 15)
    for bad in ({"every": "custom", "times": [], "group": "all"}, {"every": "custom", "times": ["25:00"], "group": "all"},
                {"every": "custom", "times": ["08:00"], "group": "sometimes"}, {"every": "custom", "times": ["08:00"]},
                {"every": "custom", "times": ["08:00"], "days": [7]}, {"every": "custom", "times": ["08:00"] * 13, "group": "all"}):
        with pytest.raises(ValueError):
            R.validate({"kind": "agent", "goal": "x", "schedule": bad})


# ---- Aurora's code in its own cage ------------------------------------------------------------------------------
@pytest.mark.skipif(not shutil.which("bwrap"), reason="bubblewrap not installed")
def test_a_project_runs_its_tests_with_no_network_and_no_secrets(cfg):
    if subprocess.run(["bwrap", "--ro-bind", "/", "/", "--", "true"], capture_output=True).returncode != 0:
        pytest.skip("no user namespaces here")
    p = cfg.path("AURORA_PROJECTS_DIR") / "demo"
    p.mkdir(parents=True)
    (p / "test_a.py").write_text("def test_ok():\n    assert 1 + 1 == 2\n")
    r = prj_run.run(cfg, "demo", "python -m pytest -q -p no:cacheprovider")
    assert r["exit"] == 0 and "1 passed" in r["output"]
    r = prj_run.run(cfg, "demo", "python -c \"import socket; socket.create_connection(('1.1.1.1', 443), 3)\"")
    assert r["exit"] != 0                                               # no network
    r = prj_run.run(cfg, "demo", f"cat {cfg.env_file}; env")
    assert "test-secret-" not in r["output"] and "AURORA_" not in r["output"]
    r = prj_run.run(cfg, "demo", "echo x > made.txt && echo y > /etc/aurora-test")
    assert (p / "made.txt").exists() and r["exit"] != 0
    for bad in ("../x", "Demo", ""):
        with pytest.raises(ValueError):
            prj_run.run(cfg, bad, "true")


# ---- the notifications that were missing ---------------------------------------------------------------------
def test_every_event_aurora_tells_has_a_kind_the_owner_can_choose():
    for ev, (kind, _view, titles) in sys_push.TEXTS.items():
        assert kind == "test" or kind in sys_push.KINDS, ev
        assert titles["it"] and titles["en"]
    for ev, kind in (("health.down", "health"), ("device.new", "access"), ("social.auto", "social"),
                     ("forge.request", "plugin")):
        assert sys_push.TEXTS[ev][0] == kind
    assert "health" in sys_push.MACHINE and "access" not in sys_push.MACHINE and "social" not in sys_push.MACHINE


def test_a_service_down_is_told_once_and_its_return_too():
    from aurora.sys_health import health_change
    ok = [{"name": "aurora-llm", "level": "ok", "text": "attivo"}]
    down = [{"name": "aurora-llm", "level": "down", "text": "fermo"}]
    assert health_change(ok, set()) is None
    assert health_change(down, set()) == ("health.down", "aurora-llm: fermo")
    assert health_change(down, {"aurora-llm"}) is None                  # still down: not said again
    assert health_change(ok, {"aurora-llm"}) == ("health.up", "aurora-llm")


# ---- the search beyond arXiv --------------------------------------------------------------------------------------
class _Resp:
    def __init__(self, data=None, text="", content=b""):
        self._d, self.text, self.content = data, text, content

    def json(self):
        return self._d


def test_the_other_sources_give_candidates_and_their_documents_on_demand():
    from aurora import kno_acquire_more as M
    calls = []

    def get(url, **p):
        calls.append(url)
        if url.endswith("/search") and "europepmc" in url:
            return _Resp({"resultList": {"result": [
                {"pmcid": "PMC1", "title": "Off-target", "license": "cc by", "abstractText": "<b>CRISPR</b> errors"},
                {"pmcid": "PMC2", "title": "No abstract", "meshHeadingList": {"meshHeading": [{"descriptorName": "Genes"}]}},
                {"title": "no pmcid: skipped"}]}})
        if url.endswith("fullTextXML"):
            return _Resp(content=b"<article><front><article-meta><title-group><article-title>T</article-title></title-group>"
                                 b"</article-meta></front><body><p>" + b"text " * 200 + b"</p></body></article>")
        if "wikipedia" in url and p.get("list") == "search":
            return _Resp({"query": {"search": [{"title": "Stoicism", "snippet": "a <span>school</span>"}]}})
        if "wikipedia" in url:
            return _Resp({"query": {"pages": {"1": {"title": "Stoicism", "extract": "Body\n== References ==\nx"}}}})
        if "api.github.com" in url:
            return _Resp({"items": [{"full_name": "a/b", "description": "db", "license": {"spdx_id": "MIT"},
                                     "default_branch": "main", "html_url": "https://github.com/a/b"},
                                    {"full_name": "c/d", "license": {"spdx_id": "NOASSERTION"}}]})
        return _Resp(text="# README " + "x" * 900)
    e = M.europepmc(get, "crispr", 5)
    assert [x.arxiv_id for x in e] == ["europepmc:PMC1", "europepmc:PMC2"] and e[0].abstract == "CRISPR errors"
    assert e[1].abstract == "Genes" and e[0].source == "europepmc" and not any("fullTextXML" in c for c in calls)
    name, data, lic, url = e[0].fetch()                               # fetched only when chosen
    assert name == "PMC1.txt" and b"text" in data and lic == "cc by"
    w = M.wikipedia(get, "stoic", 5)
    assert w[0].abstract == "a school" and w[0].fetch()[1] == b"Body"   # the references cut away
    g = M.github(get, "vector database", 5)
    assert [x.arxiv_id for x in g] == ["github:a/b"] and g[0].fetch()[2] == "MIT"   # only an open licence


def test_a_document_goes_to_a_domain_of_its_source():
    from aurora import kno_acquire_more as M

    class LLM:
        def __init__(self, reply):
            self.reply = reply

        def complete(self, system, user, n):
            return type("A", (), {"answer": self.reply})()
    assert "medicine" in M.domains_of("europepmc") and M.domains_of("github") == ["programming"]
    assert M.choose_domain(LLM("genomics"), "europepmc", "q", "t") == "genomics"
    assert M.choose_domain(LLM("astrology"), "wikipedia", "q", "t") == M.domains_of("wikipedia")[0]   # never outside
    assert M.choose_domain(LLM("whatever"), "github", "q", "t") == "programming"


# ---- security: the owner's checks, the documentation, the firewall's API ---------------------------------------
def _fw_line(ts, **kv):
    return f"{ts} INFO aurora.firewall 192.0.2.1 <29>" + " ".join(f'{k}="{v}"' for k, v in kv.items()) + "\n"


def test_a_rule_is_checked_and_counts_per_source():
    from aurora import sec_rules
    for bad in ({"id": "Bad Id", "match": {"x": "y"}}, {"id": "a", "match": {}}, {"id": "a", "match": {"x": "y"}, "threshold": 0},
                {"id": "a", "match": {"bad field!": "y"}}):
        with pytest.raises(ValueError):
            sec_rules.check(bad)
    r = sec_rules.check({"id": "appliance_denied", "match": {"log_component": "Appliance Access", "log_id": "010302"},
                         "threshold": 3, "window_min": 10, "on": True})
    rs = sec_rules.RuleSet([r])
    line = {"log_component": "appliance access", "log_id": "010302600001", "_raw": "x"}
    assert rs.feed(line, "1.2.3.4", 0) == [] and rs.feed(line, "5.6.7.8", 1) == []
    assert rs.feed(line, "1.2.3.4", 2) == [] and len(rs.feed(line, "1.2.3.4", 3)) == 1          # 3 from one source
    assert rs.feed(line, "1.2.3.4", 4) == []                                                     # once an hour
    assert rs.feed({**line, "log_id": "019999"}, "9.9.9.9", 5) == []                             # another log_id
    assert sec_rules.RuleSet([{**r, "on": False}]).rules == []


def test_the_traffic_is_grouped_and_a_proposal_out_of_it_is_dropped(cfg):
    from datetime import datetime
    from aurora import sec_profile
    d = cfg.path("AURORA_LOG_DIR") / "firewall"
    d.mkdir(parents=True)
    now = datetime.now().astimezone().isoformat(timespec="milliseconds")
    old = "2020-01-01T00:00:00.000+02:00"
    with open(d / "firewall.log", "w") as fh:
        for _ in range(5):
            fh.write(_fw_line(now, log_id="010302600001", log_type="Firewall", log_component="Appliance Access",
                              log_subtype="Denied", src_ip="203.0.113.9", device_serial_id="SERIAL123"))
        fh.write(_fw_line(old, log_id="010101600001", log_type="Firewall", log_component="Firewall Rule"))
    groups = sec_profile.observe(cfg, 24)
    assert len(groups) == 1 and groups[0]["count"] == 5 and groups[0]["log_id"] == "010302"
    assert "203.0.113.9" not in json.dumps(groups) and "SERIAL123" not in json.dumps(groups)   # never sent out

    class LLM:
        def complete(self, system, user, n):
            assert "203.0.113.9" not in user
            return type("A", (), {"answer": json.dumps([
                {"id": "denied_admin", "title": "t", "match": {"log_component": ["Appliance Access"]}, "threshold": 50,
                 "window_min": 10, "action": "bloccare"},
                {"id": "invented", "match": {"made_up_field": "x"}, "threshold": 1, "window_min": 1},
                {"id": "BROKEN"}])})()
    got = sec_profile.proposals(LLM(), "doc", groups)
    assert [r["id"] for r in got] == ["denied_admin"] and got[0]["on"] is False


def test_the_firewall_api_blocks_only_on_good_addresses(cfg, monkeypatch):
    from aurora import sec_xg
    cfg.values.update(AURORA_XG_API_URL="https://192.0.2.1:4444", AURORA_XG_API_USER="aurora",
                      AURORA_XG_API_PASSWORD="p<w>&d", AURORA_XG_VERIFY_TLS=False, AURORA_XG_BLOCK_GROUP="Aurora-Blocklist")
    for bad in ("127.0.0.1", "192.0.2.1", "not-an-ip", "224.0.0.1", "::1"):
        with pytest.raises(sec_xg.XGError):
            sec_xg.blockable(cfg, bad)
    sent = []

    class R:
        status_code = 200
        text = '<Response><IPHost transactionid=""><Status code="200">Configuration applied successfully.</Status></IPHost></Response>'
    monkeypatch.setattr(sec_xg.httpx, "post", lambda url, files, timeout, verify: sent.append((url, files["reqxml"][1])) or R())
    out = sec_xg.block(cfg, "203.0.113.9", "port scan <x>")
    assert out["blocked"] == "203.0.113.9" and sent[0][0] == "https://192.0.2.1:4444/webconsole/APIController"
    xml = sent[1][1]
    assert "<Password>p&lt;w&gt;&amp;d</Password>" in xml                       # escaped, never injected
    assert "<IPHost><Name>aurora-block-203.0.113.9</Name>" in xml and "<HostGroup>Aurora-Blocklist</HostGroup>" in xml
    assert "port scan &lt;x&gt;" in xml and "<IPHostGroup><Name>Aurora-Blocklist</Name>" in sent[0][1]

    class Refused(R):
        text = "<Response><Login><status>Authentication Failure</status></Login></Response>"
    monkeypatch.setattr(sec_xg.httpx, "post", lambda *a, **k: Refused())
    with pytest.raises(sec_xg.XGError, match="refused the login"):
        sec_xg.test(cfg)


def test_a_proposal_is_played_on_the_real_traffic_before_the_owner_decides(cfg):
    from datetime import datetime, timedelta
    from aurora import sec_profile, sec_rules
    d = cfg.path("AURORA_LOG_DIR") / "firewall"
    d.mkdir(parents=True)
    t0 = datetime.now().astimezone() - timedelta(hours=2)
    with open(d / "firewall.log", "w") as fh:
        for i in range(12):                                   # 12 denials from one source in 2 minutes
            fh.write(_fw_line((t0 + timedelta(seconds=10 * i)).isoformat(timespec="milliseconds"), log_id="010302600001",
                              log_component="Appliance Access", src_ip="203.0.113.9"))
    r = sec_rules.check({"id": "denied", "match": {"log_id": "010302"}, "threshold": 10, "window_min": 5})
    [out] = sec_profile.tried(cfg, [r], 24)
    assert out["tried"] == {"incidents": 1, "sources": 1, "hours": 24} and sec_rules.check(out)["tried"] == out["tried"]
