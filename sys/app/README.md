# Aurora's Android app

Aurora's own app for Android, outside any store: the WebUI in a window of its own, plus what a web app cannot do — a
line kept open to Aurora for her notifications, and calls between the phone and Aurora with no third-party service.
The phone talks only to Aurora's HTTPS address.

## Install

1. Download `aurora-app-<version>.apk` from the release on GitHub (or from Aurora's 📱 page, which offers the newest
   one built on that machine) and open it on the phone; Android asks to allow apps from that source.
2. First start: «Start», Aurora's address (IP or name) and port (empty = 443, always HTTPS), «Connect», then the
   WebUI's login (a registered device).
3. After that it opens by itself. To change the address: long press on the icon.

An update installs over the app only when it is signed with the same key. The releases are signed with the key whose
certificate's SHA-256 is `ddd4944a027e41b13a8e3644d66393dad98fcb88e90e8ab5a611c4b80c7eaf21`
(`apksigner verify --print-certs aurora-app-<version>.apk`).

## What it does

| Phase | What | Since |
|---|---|---|
| F1 | **Window**: welcome, address and port, the WebUI's login, then it enters by itself. The microphone only for Aurora's pages, outside links in the browser, files up and down. | 0.1.0 |
| F2 | **Line**: a foreground service keeps a long request open to Aurora (`GET /v1/aurora/line`, HTTPS, no new port); notifications arrive through it (a WebView gets no Web Push). | 0.2.1 |
| F3 | **Calls**: full-screen ring even with the phone locked, answer or decline from the notification; voice at 16 kHz on a WebSocket over the HTTPS port, with Android's echo canceller and noise suppressor. | 0.3.0 |
| F3 | **Calling Aurora**: the 📞 in the chat's bar (in the app only) opens the call screen already answered. | 0.4.0 |

The server's side is in Aurora's code: `sys_line` and `api/line` (the line), `sys_call` and `api/call` (calls),
`sys_phone_app` and `api/phone_app` (the 📱 page that offers the APK).

## Build

Without Gradle: `build.py` uses aapt2, javac, d8, zipalign and apksigner from `tools/` (JDK 21 and Android SDK 36,
ignored by git). The signing key is made on the first build in `keys/` (0600, ignored by git) and must be kept and
backed up, never made again.

    python sys/app/build.py --to <AURORA_STATUS_DIR>/app   # the 📱 page offers it
    python sys/app/build.py --dist                         # the APK published with the code, attached to the release

Tests: `sys/core/tests/test_app_android.py` (permissions, HTTPS only, the address rules, the JavaScript bridge, the
call; the build itself when `tools/` is there).

## License

Apache License 2.0 — see the repository's [LICENSE](../../LICENSE).
