# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's Android app (sys/app, README.md), its APK built without Gradle: aapt2 (resources and manifest), javac, d8,
zipalign, apksigner, all from tools/ (the JDK and the Android SDK, ignored by git).

    python sys/app/build.py            -> out/aurora-app-<version>.apk, signed with keys/aurora-app.jks
    python sys/app/build.py --to DIR   -> and a copy in DIR: Aurora's <AURORA_STATUS_DIR>/app, offered by the WebUI's
                                          📱 page (the newest version there is the one downloaded)
    python sys/app/build.py --dist     -> and the only APK in dist/: the one published with the code and attached to
                                          the GitHub release (.github/workflows/release.yml)

The signing key is made on the first build (keys/, 0600, ignored by git): an update installs over the app only when it
is signed with the same key, so keys/ is kept and backed up, never made again.
"""
from __future__ import annotations

import os
import secrets
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

VERSION, CODE = "0.4.1", 7                   # versionName and versionCode (the code grows by one at every release)
MIN_SDK, TARGET_SDK, BUILD_TOOLS = 29, 36, "36.0.0"
PACKAGE = "org.aurora.app"

ROOT = Path(__file__).resolve().parent
APP, TOOLS, KEYS, OUT, DIST = ROOT / "android", ROOT / "tools", ROOT / "keys", ROOT / "out", ROOT / "dist"
JDK, SDK = TOOLS / "jdk", TOOLS / "sdk"
BT = SDK / "build-tools" / BUILD_TOOLS
JAR = SDK / "platforms" / f"android-{TARGET_SDK}" / "android.jar"


def run(*args, **kw) -> subprocess.CompletedProcess:
    env = {**os.environ, "JAVA_HOME": str(JDK), "PATH": f"{JDK / 'bin'}:{os.environ.get('PATH', '')}"}
    r = subprocess.run([str(a) for a in args], capture_output=True, text=True, env=env, **kw)
    if r.returncode:
        raise RuntimeError(f"{Path(str(args[0])).name} failed:\n{(r.stderr or r.stdout)[-3000:]}")
    return r


def missing() -> list[str]:
    """The tools a build needs that are not in tools/ (empty: ready)."""
    need = [JDK / "bin" / "javac", BT / "aapt2", BT / "d8", BT / "zipalign", BT / "apksigner", JAR]
    return [str(p.relative_to(ROOT)) for p in need if not p.exists()]


def key() -> tuple[Path, str]:
    """The signing key and its password, made once."""
    jks, pw = KEYS / "aurora-app.jks", KEYS / "password"
    if not jks.exists():
        KEYS.mkdir(mode=0o700, exist_ok=True)
        secret = secrets.token_urlsafe(24)
        pw.write_text(secret)
        pw.chmod(0o600)
        run(JDK / "bin" / "keytool", "-genkeypair", "-keystore", jks, "-storepass", secret, "-keypass", secret,
            "-alias", "aurora", "-keyalg", "RSA", "-keysize", "4096", "-validity", "36500", "-dname", "CN=Aurora app")
        jks.chmod(0o600)
    return jks, pw.read_text().strip()


def copy(apk: Path, dest: Path, alone: bool = False) -> Path:
    """The APK copied into `dest` whole (the page never offers a half-copied file); `alone`: older ones removed."""
    dest.mkdir(parents=True, exist_ok=True)
    tmp = dest / (apk.name + ".part")
    shutil.copyfile(apk, tmp)
    tmp.replace(dest / apk.name)
    for old in dest.glob("aurora-app-*.apk") if alone else []:
        if old.name != apk.name:
            old.unlink()
    return dest / apk.name


def build() -> Path:
    if missing():
        raise RuntimeError(f"tools missing: {', '.join(missing())}")
    work = OUT / "work"
    shutil.rmtree(work, ignore_errors=True)
    (work / "gen").mkdir(parents=True)
    (work / "classes").mkdir()
    # resources and manifest; R.java for the code
    run(BT / "aapt2", "compile", "--dir", APP / "res", "-o", work / "res.zip")
    run(BT / "aapt2", "link", "-o", work / "base.apk", "-I", JAR, "--manifest", APP / "AndroidManifest.xml",
        "--min-sdk-version", MIN_SDK, "--target-sdk-version", TARGET_SDK, "--version-code", CODE,
        "--version-name", VERSION, "--java", work / "gen", work / "res.zip")
    conf = work / "gen" / PACKAGE.replace(".", "/") / "BuildConfig.java"
    conf.write_text(f'package {PACKAGE};\n\n/** Written by sys/app/build.py. */\nfinal class BuildConfig {{\n'
                    f'    static final String VERSION = "{VERSION}";\n    private BuildConfig() {{}}\n}}\n')
    sources = sorted(str(p) for p in (APP / "java").rglob("*.java")) + sorted(str(p) for p in (work / "gen").rglob("*.java"))
    run(JDK / "bin" / "javac", "-source", "17", "-target", "17", "-encoding", "UTF-8", "-Xlint:-options",
        "-classpath", JAR, "-d", work / "classes", *sources)
    classes = sorted(str(p) for p in (work / "classes").rglob("*.class"))
    run(BT / "d8", "--release", "--min-api", MIN_SDK, "--lib", JAR, "--output", work, *classes)
    with zipfile.ZipFile(work / "base.apk", "a", zipfile.ZIP_DEFLATED) as z:
        z.write(work / "classes.dex", "classes.dex")
    run(BT / "zipalign", "-f", "-p", "4", work / "base.apk", work / "aligned.apk")
    jks, secret = key()
    apk = OUT / f"aurora-app-{VERSION}.apk"
    run(BT / "apksigner", "sign", "--ks", jks, "--ks-pass", f"pass:{secret}", "--ks-key-alias", "aurora",
        "--out", apk, work / "aligned.apk")
    run(BT / "apksigner", "verify", apk)
    return apk


if __name__ == "__main__":
    try:
        out = build()
        if "--to" in sys.argv:
            print(copy(out, Path(sys.argv[sys.argv.index("--to") + 1])))
        if "--dist" in sys.argv:
            print(copy(out, DIST, alone=True))
        print(out)
    except RuntimeError as e:
        sys.exit(str(e))
