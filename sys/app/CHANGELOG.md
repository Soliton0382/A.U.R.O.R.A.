# Aurora's Android app — changelog

## 0.4.0 - 2026-10-26

- Calling Aurora: the 📞 in the chat's bar (in the app only) opens the call screen already answered
  (`AuroraApp.callAurora`, a new bridge method that takes only a call id); Aurora prepares the call with
  `POST /v1/aurora/call/dial`, rings no phone, and answers «Ciao, dimmi pure.».

## 0.3.1 - 2026-10-25

- A call answered on another phone stops ringing here (the line's «call_answered» event).

## 0.3.0 - 2026-10-25

- F3: calls. Full-screen ring even with the phone locked (full-screen intent, call style, insistent ringtone),
  answer or decline from the notification too; in a call: time, lines, mute, speaker, hang up; screen off at the ear.
  Voice at 16 kHz on a WebSocket (its own client, `Ws`) on the HTTPS port, with Android's echo canceller and noise
  suppressor.
- A notification tapped with the WebUI already open changes page without reloading.
- The full-screen notification permission asked once (Android 14+).

## 0.2.1 - 2026-10-25

- F2: the line (LineService, a «remoteMessaging» foreground service): `GET /v1/aurora/line` held open 50 s, the
  notifications chosen for push arrive with no third-party service; it starts with the app, when the page is loaded
  and when the phone starts; it stops when the login is no longer valid. A tapped notification opens the right page.
- Notifications and battery: the permission asked once, the battery saver's exemption asked once.
- A bridge for the WebUI (`AuroraApp.notifications()`, `AuroraApp.settings()`): the 🔔 shows in the app too.
- `build.py --to DIR`: the APK copied where the WebUI offers it.

## 0.1.0 - 2026-10-25

- F1: the WebUI in a window (welcome, address and port, the WebUI's login, the microphone only for Aurora), built
  without Gradle (build.py).
