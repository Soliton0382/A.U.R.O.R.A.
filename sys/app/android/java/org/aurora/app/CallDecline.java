// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
package org.aurora.app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** «Rifiuta» on the ringing notification, without opening the app. */
public class CallDecline extends BroadcastReceiver {
    @Override
    public void onReceive(Context c, Intent i) {
        String id = i.getStringExtra(CallActivity.ID);
        String base = c.getSharedPreferences(MainActivity.PREFS, Context.MODE_PRIVATE).getString(MainActivity.ADDRESS, null);
        if (id == null || base == null) return;
        CallActivity.stopRinging(c, id);
        CallActivity.over(id);
        CallActivity.decline(c, base, id);
    }
}
