# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C594, the audit of 12 Nov, the WebUI and the Android app: the page's policy from the API itself, a link only when it
is a web address, an artifact without WebRTC; in the app the key for the WebUI's page only, the assistant's screen for
the app and the system only, nothing but web addresses handed to other apps. The Java is read (and Address compiled
when the tools are there): the phone itself is not tried here."""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from aurora import doc_artifact, net_https
from test_app_android import MAIN, MANIFEST, ROOT, build, needs_tools

HERE = Path(__file__).resolve().parent
JS = HERE.parent / "webui" / "js"


# ---- G4 -------------------------------------------------------------------------------------------------------------
def test_the_api_itself_sends_the_webui_s_policy(tmp_path):
    from conftest import write_env
    env = write_env(tmp_path)
    r = subprocess.run([sys.executable, str(HERE / "api_c594.py"), str(tmp_path)], capture_output=True, text=True,
                       timeout=300, env={**{k: os.environ[k] for k in ("SYSTEMROOT",) if k in os.environ},
                                         "PATH": "/usr/bin:/bin", "AURORA_ENV_FILE": str(env)})
    assert r.returncode == 0, r.stderr[-3000:]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    for path, h in out.items():
        assert h["status"] == 200, (path, h)
        assert h["csp"] == net_https.CSP and "script-src 'self'" in h["csp"] and h["nosniff"] == "nosniff", (path, h)


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_only_a_web_address_becomes_a_link():
    cases = {"https://example.org/a": [True, "https://example.org/a", "_blank"],
             "http://example.org/a": [True, "http://example.org/a", None],
             "/v1/aurora/uploads/0123456789abcdef": [True, "/v1/aurora/uploads/0123456789abcdef", None],
             "javascript:alert(1)": [False, None, None], " JavaScript:alert(1)": [False, None, None],
             "data:text/html,<script>alert(1)</script>": [False, None, None],
             "vbscript:x": [False, None, None], "intent://x#Intent;end": [False, None, None]}
    out = subprocess.run(["node", str(HERE / "js" / "dom_links.mjs"), (JS / "dom.js").as_uri(), json.dumps(list(cases))],
                         capture_output=True, text=True, timeout=30, check=True).stdout
    assert dict(zip(cases, json.loads(out))) == cases


def test_addresses_from_outside_reach_a_link_only_through_the_check():
    """The sinks fed by a web source, a plugin's manifest, another user's contact page, a repository, the model."""
    for name, value in (("modules/today.js", "w.url"), ("modules/today.js", "n.link"), ("modules/people.js", "s.url"),
                        ("modules/plugins.js", "l.url"), ("modules/project_papers.js", "w.url"),
                        ("modules/consoles.js", "it.url")):
        text = (JS / name).read_text()
        assert f"if (safeUrl({value})) a.href = {value};" in text, (name, value)
        assert not re.search(rf"(?<!\) )a\.href = {re.escape(value)}", text) and f"href: {value}" not in text, (name, value)
    assert "safeUrl(r.homepage)" in (JS / "modules" / "projects.js").read_text()
    assert 'case "open_url": return safeUrl(p.url) ? p.url : "";' in (JS / "phone.js").read_text()


# ---- G6 -------------------------------------------------------------------------------------------------------------
def test_an_artifact_has_no_webrtc():
    assert "webrtc 'block'" in doc_artifact.CSP and "connect-src 'none'" in doc_artifact.CSP


# ---- G1, G3, G5: the app --------------------------------------------------------------------------------------------
def test_the_key_goes_to_the_webui_s_page_only_and_every_bridge_call_needs_it():
    finished = MAIN.split("public void onPageFinished(")[1].split("\n            }\n")[0]
    assert "if (Address.home(base, url) && Address.home(base, v.getUrl()))" in finished
    assert finished.index("Address.home(base, url)") < finished.index("window.AuroraAppKey=")
    bridge = MAIN.split("final class Bridge {")[1].split("\n    }\n")[0]
    for method in re.findall(r"@JavascriptInterface\s+(?:/\*\*.*?\*/\s+)?public \w+ \w+\([^)]*\) \{.*?\n        \}\n", bridge, re.S):
        assert "mine(k)" in method, method                           # no action, no answer without the page's key
    assert "!Address.home(base, page)" in bridge
    push = (JS / "push.js").read_text()
    assert 'app("notifications")' in push and 'app("settings")' in push and "a[name](window.AuroraAppKey" in push


def test_a_page_hands_only_web_addresses_to_other_apps():
    outside = MAIN.split("private void outside(Uri u) {")[1].split("\n    }\n")[0]
    assert outside.index("!Address.web(u.toString())) return;") < outside.index("startActivity(")


@needs_tools
def test_the_app_s_page_and_web_rules(tmp_path):
    """Address.home and Address.web compiled with the JDK and run against a small table, off the phone."""
    check = tmp_path / "Check.java"
    check.write_text("""package org.aurora.app;
public class Check { public static void main(String[] a) {
  String b = "https://aurora.example:8443";
  String[] home = {b, b + "/", b + "/?view=chat", b + "/#x"};
  String[] not = {b + "/v1/preview/art-abc/index.html", b + "/v1/aurora/uploads/0123456789abcdef", b + "/static/index.html",
                  "https://evil.example:8443/", "http://aurora.example:8443/", b + "//", "about:blank", null};
  for (String u : home) if (!Address.home(b, u)) throw new AssertionError("home: " + u);
  for (String u : not) if (Address.home(b, u)) throw new AssertionError("not home: " + u);
  String[] web = {"https://example.org/a", "http://example.org", "HTTPS://example.org"};
  String[] other = {"tel:+390000000", "sms:+390000000", "intent://x#Intent;end", "file:///sdcard/x", "content://x/y",
                    "javascript:alert(1)", "market://details?id=x", "mailto:a@example.org", "", "not a url"};
  for (String u : web) if (!Address.web(u)) throw new AssertionError("web: " + u);
  for (String u : other) if (Address.web(u)) throw new AssertionError("not web: " + u);
  System.out.println("ok"); } }""")
    out = tmp_path / "c"
    src = ROOT / "android" / "java" / "org" / "aurora" / "app" / "Address.java"
    subprocess.run([build.JDK / "bin" / "javac", "-d", out, src, check], check=True, capture_output=True)
    r = subprocess.run([build.JDK / "bin" / "java", "-cp", out, "org.aurora.app.Check"], capture_output=True, text=True)
    assert r.stdout.strip() == "ok", r.stderr


# ---- G2 -------------------------------------------------------------------------------------------------------------
def test_the_assistant_s_screen_opens_for_the_app_and_the_system_only():
    assert '<permission android:name="org.aurora.app.permission.ASSIST" android:protectionLevel="signature" />' in MANIFEST
    tag = MANIFEST.split('".AssistActivity"')[1].split(">")[0]
    assert 'android:permission="org.aurora.app.permission.ASSIST"' in tag
    assist = MANIFEST.split('".AssistActivity"')[1].split("</activity>")[0]
    assert "android.intent.action.ASSIST" in assist                  # the system's entry stays
    assert "uses-permission android:name=\"org.aurora.app.permission.ASSIST\"" not in MANIFEST
    shortcuts = (ROOT / "android" / "res" / "xml" / "shortcuts.xml").read_text()
    assert 'android:targetPackage="org.aurora.app" android:targetClass="org.aurora.app.AssistActivity"' in shortcuts
