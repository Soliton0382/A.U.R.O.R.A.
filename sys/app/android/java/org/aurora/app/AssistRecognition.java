// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
package org.aurora.app;

import android.content.Intent;
import android.speech.RecognitionService;
import android.speech.SpeechRecognizer;

/**
 * Android lists an assistant only with a recognition service of its own: this one answers that it cannot, so other
 * apps keep the phone's own recognizer; Aurora's speech is understood by Aurora (Whisper), in the chat.
 */
public class AssistRecognition extends RecognitionService {
    @Override
    protected void onStartListening(Intent i, Callback cb) {
        try { cb.error(SpeechRecognizer.ERROR_CLIENT); } catch (android.os.RemoteException e) { /* the caller left */ }
    }

    @Override
    protected void onCancel(Callback cb) {}

    @Override
    protected void onStopListening(Callback cb) {}
}
