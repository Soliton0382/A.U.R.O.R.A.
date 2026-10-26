// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
package org.aurora.app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** The line again after the phone restarts, or after the app is updated. */
public class Boot extends BroadcastReceiver {
    @Override
    public void onReceive(Context c, Intent i) {
        String a = i.getAction();
        if (Intent.ACTION_BOOT_COMPLETED.equals(a) || Intent.ACTION_MY_PACKAGE_REPLACED.equals(a)) LineService.start(c);
    }
}
