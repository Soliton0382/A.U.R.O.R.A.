// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
package org.aurora.app;

import android.service.voice.VoiceInteractionService;

/**
 * Aurora as the phone's assistant (N68, owner, 1 Nov: «arriviamo ad una app che installo e posso già aprire Google
 * assistant»): chosen in Settings → Apps → Default apps → Digital assistant, the long press or the gesture calls
 * Aurora (AssistSessionService; owner, 1 Nov: «gestire aurora assistente come se fosse una chiamata ad aurora ma con
 * la gestione delle azioni cellulare»). Nothing listens in the background: no hotword.
 */
public class AssistService extends VoiceInteractionService {
}
