// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
package org.aurora.app;

import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.service.voice.VoiceInteractionSession;
import android.service.voice.VoiceInteractionSessionService;

/** The assistant asked (a long press, the gesture): a call to Aurora on its own screen, on the loudspeaker (AssistActivity). */
public class AssistSessionService extends VoiceInteractionSessionService {
    @Override
    public VoiceInteractionSession onNewSession(Bundle args) {
        return new Session(this);
    }

    static final class Session extends VoiceInteractionSession {
        Session(Context c) { super(c); }

        @Override
        public void onShow(Bundle args, int flags) {
            super.onShow(args, flags);
            Intent i = new Intent(getContext(), AssistActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            try {
                startAssistantActivity(i);
            } catch (SecurityException | IllegalStateException e) {
                getContext().startActivity(i);
            }
            hide();
        }
    }
}
