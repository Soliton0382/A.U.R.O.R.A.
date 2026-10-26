# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's Android app (sys/app) as built: what it asks, what it trusts, how it treats an address, the APK published
with the code. The build needs sys/app/tools (skipped without: the mirror, CI)."""
import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "app"
_spec = importlib.util.spec_from_file_location("app_build", ROOT / "build.py")
build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build)
MANIFEST = (ROOT / "android" / "AndroidManifest.xml").read_text()
MAIN = (ROOT / "android" / "java" / "org" / "aurora" / "app" / "MainActivity.java").read_text()
needs_tools = pytest.mark.skipif(bool(build.missing()), reason="tools/ not installed")


def test_only_the_permissions_the_app_uses():
    asked = set(re.findall(r'uses-permission android:name="android\.permission\.(\w+)"', MANIFEST))
    assert asked == {"INTERNET", "RECORD_AUDIO", "MODIFY_AUDIO_SETTINGS",                    # phase 1
                     "FOREGROUND_SERVICE", "FOREGROUND_SERVICE_REMOTE_MESSAGING", "POST_NOTIFICATIONS",  # phase 2
                     "RECEIVE_BOOT_COMPLETED", "REQUEST_IGNORE_BATTERY_OPTIMIZATIONS",
                     "USE_FULL_SCREEN_INTENT", "WAKE_LOCK", "VIBRATE"}                                  # phase 3


def test_the_line_sends_only_the_login_to_aurora_and_stops_when_it_is_gone():
    line = (ROOT / "android" / "java" / "org" / "aurora" / "app" / "LineService.java").read_text()
    assert '"/v1/aurora/line"' in line and "CookieManager.getInstance().getCookie(url)" in line
    assert "code == 401 || code == 403" in line and "throw new Gone()" in line
    assert 'android:exported="false"' in MANIFEST.split(".LineService")[1].split("/>")[0]


def test_https_only_and_no_secret_accepted_certificate():
    net = (ROOT / "android" / "res" / "xml" / "network.xml").read_text()
    assert 'cleartextTrafficPermitted="false"' in net and 'src="user"' in net
    assert "h.cancel()" in MAIN and "h.proceed" not in MAIN          # a bad certificate is never accepted
    assert 'allowBackup="false"' in MANIFEST                          # the device's login is not copied off the phone


def test_the_microphone_only_for_aurora_pages():
    body = MAIN.split("private void answer(PermissionRequest r)")[1].split("\n    }\n")[0]
    assert "Address.inside(base, r.getOrigin().toString())" in body and "r.deny()" in body
    assert "RESOURCE_VIDEO_CAPTURE" not in MAIN


def test_no_address_of_this_machine_in_the_sources():
    text = "".join(p.read_text() for p in (ROOT / "android").rglob("*") if p.is_file())
    assert not re.search(r"\b(?:192\.168|10\.\d+\.\d+)\.\d+", text)
    assert "aurora.example" in text                                   # the hint is a placeholder (RFC 2606)


@needs_tools
def test_the_address_rules(tmp_path):
    """Address.java compiled with the JDK and run against a small table, off the phone."""
    check = tmp_path / "Check.java"
    check.write_text("""package org.aurora.app;
public class Check { public static void main(String[] a) {
  String[][] n = {{"aurora.example:8443", "https://aurora.example:8443"}, {" HTTPS://Aurora.Example/x ", "https://aurora.example"},
                  {"https://aurora.example:443", "https://aurora.example"}, {"http://aurora.example", null},
                  {"https://user@aurora.example", null}, {"", null}, {"https://", null}};
  for (String[] c : n) { String o = Address.normalize(c[0]); if (o == null ? c[1] != null : !o.equals(c[1])) throw new AssertionError(c[0] + " -> " + o); }
  String[][] f = {{"aurora.example", "", "https://aurora.example"}, {"aurora.example", "8443", "https://aurora.example:8443"},
                  {"203.0.113.7", "8443", "https://203.0.113.7:8443"}, {"https://aurora.example:9000", "443", "https://aurora.example"},
                  {"aurora.example", "0", null}, {"aurora.example", "70000", null}, {"aurora.example", "84a", null}, {"", "8443", null}};
  for (String[] c : f) { String o = Address.of(c[0], c[1]); if (o == null ? c[2] != null : !o.equals(c[2])) throw new AssertionError(c[0] + ":" + c[1] + " -> " + o); }
  String b = "https://aurora.example:8443";
  if (!Address.inside(b, "https://aurora.example:8443/v1/x")) throw new AssertionError("same origin");
  if (Address.inside(b, "https://aurora.example/x") || Address.inside(b, "https://evil.example:8443/")
      || Address.inside(b, "http://aurora.example:8443/") || Address.inside(null, b)) throw new AssertionError("other origin");
  System.out.println("ok"); } }""")
    out = tmp_path / "c"
    src = ROOT / "android" / "java" / "org" / "aurora" / "app" / "Address.java"
    subprocess.run([build.JDK / "bin" / "javac", "-d", out, src, check], check=True, capture_output=True)
    r = subprocess.run([build.JDK / "bin" / "java", "-cp", out, "org.aurora.app.Check"], capture_output=True, text=True)
    assert r.stdout.strip() == "ok", r.stderr


@needs_tools
def test_the_apk_builds_signed():
    apk = build.build()
    dump = subprocess.run([build.BT / "aapt2", "dump", "badging", apk], capture_output=True, text=True, check=True).stdout
    assert f"name='{build.PACKAGE}' versionCode='{build.CODE}' versionName='{build.VERSION}'" in dump
    assert f"minSdkVersion:'{build.MIN_SDK}'" in dump and f"targetSdkVersion:'{build.TARGET_SDK}'" in dump
    v = subprocess.run([build.BT / "apksigner", "verify", "--print-certs", apk], capture_output=True, text=True,
                       env={"PATH": f"{build.JDK / 'bin'}:/usr/bin:/bin"}, check=True).stdout
    assert "CN=Aurora app" in v


def test_the_page_can_ask_the_app_only_about_its_notifications_and_to_call_aurora():
    bridge = MAIN.split("final class Bridge {")[1].split("\n    }\n")[0]
    assert re.findall(r"@JavascriptInterface\s+public \w+ (\w+)\(", bridge) == ["notifications", "settings", "callAurora"]
    call = bridge.split("public void callAurora(")[1]
    assert 'id.matches("[0-9a-f]{16}")' in call and "CallActivity.ANSWER" in call      # only a call id, opened answered


def test_the_call_goes_only_to_aurora_with_the_login_and_a_checked_certificate():
    java = ROOT / "android" / "java" / "org" / "aurora" / "app"
    ws = (java / "Ws.java").read_text()
    assert "getDefaultHostnameVerifier().verify(u.getHost(), socket.getSession())" in ws   # the name, not only the chain
    assert 'replaceFirst("^https", "wss")' in ws and "http://" not in ws
    audio = (java / "CallAudio.java").read_text()
    assert 'base + "/v1/aurora/call/" + id + "/audio"' in audio and "CookieManager.getInstance().getCookie(base)" in audio
    assert "VOICE_COMMUNICATION" in audio and "AcousticEchoCanceler" in audio
    for cls in ("CallActivity", "CallDecline"):
        assert 'android:exported="false"' in MANIFEST.split(f".{cls}")[1].split(">")[0]


def test_the_apk_published_is_the_version_the_sources_say():
    """sys/app/dist holds one APK, of build.VERSION: the one the release attaches (python sys/app/build.py --dist)."""
    assert [p.name for p in (ROOT / "dist").iterdir()] == [f"aurora-app-{build.VERSION}.apk"]
    assert f"## {build.VERSION} " in (ROOT / "CHANGELOG.md").read_text()
