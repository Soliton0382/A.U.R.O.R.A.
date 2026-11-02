# Aurora's Android app — changelog

## 0.5.2 - 2026-11-02

- The assistant has its own screen (owner: «se apro l'assistente si vede il full screen dell'assistente»): the long
  press, the gesture or «Parla con Aurora» open it straight away, with no page to load. No words on it: the brain as a
  watermark, its areas lit by what Aurora is doing, the steps' icons sliding under it, the scope showing who speaks
  (blue the owner, green Aurora); ✕ or back closes it. It listens at once, with no greeting.
- WhatsApp messages open straight in WhatsApp with the text written, the contact's number put in the international
  form its link needs.
- The chat's 📞 call is the plain call again (earpiece, proximity).

## 0.5.1 - 2026-11-01

- The assistant is a call to Aurora (owner: «gestire aurora assistente come se fosse una chiamata ad aurora ma con la
  gestione delle azioni cellulare»): the long press, the gesture or «Parla con Aurora» dial her as the chat's 📞 does,
  answered and on the loudspeaker, without the proximity sensor. In the call, the message «phone» is an action done
  by `PhoneActions` and its result sent back («phone_result»), which Aurora says; a plain command («apri YouTube»,
  «timer di 5 minuti») is understood by Aurora without a model, so it is done in the time of a sentence. A call that
  hands the screen to another app ends once she has said so.

## 0.5.0 - 2026-11-01

- N68, Aurora as the phone's assistant: chosen in Settings → Apps → Default apps → Digital assistant
  (`AssistService`, `AssistSessionService`, a recognition service that declines so other apps keep the phone's own),
  the long press or the gesture opens the chat with the conversation hands-free already on; also the launcher's
  long-press shortcut «Parla con Aurora» and `ACTION_ASSIST`. Nothing listens in the background.
- Phone actions (`AuroraApp.act`, `PhoneActions`): what Aurora is asked for in the chat is handed to the phone's own
  apps — a page, a web search, an app by its name, an alarm or a timer, an event in the phone's calendar, the
  navigation, a call or a message (WhatsApp or SMS) prepared, to a number or to a contact by name. The call and the
  message are only prepared: the owner presses call or send. New permissions: the clock's alarm, the contacts (asked
  the first time a name is used).

## 0.4.1 - 2026-10-27

- Full screen for the page (the music player's visualiser): the element over everything, the system bars hidden in
  immersive mode (a swipe shows them for a moment), back or the page's own button leave it (`onShowCustomView`).

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
