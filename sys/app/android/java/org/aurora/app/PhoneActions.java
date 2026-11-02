// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
package org.aurora.app;

import android.Manifest;
import android.app.Activity;
import android.app.SearchManager;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.database.Cursor;
import android.net.Uri;
import android.provider.AlarmClock;
import android.provider.CalendarContract;
import android.provider.ContactsContract;
import android.telephony.PhoneNumberUtils;
import android.telephony.TelephonyManager;

import org.json.JSONObject;

import java.util.List;
import java.util.Locale;

/**
 * What Aurora asks the phone to do (N68, owner, 1 Nov: «l'app dovrebbe … aprire il browser fare ricerche aggiungere
 * calendar, altrimenti sarebbe solo un assistenza povero di azioni»): each action is handed to the phone's own app by
 * an intent. A call or a message is only prepared: the owner presses call or send. The answer is a word for the page:
 * "ok", "no_app", "no_contact", "need_contacts", "bad".
 */
final class PhoneActions {
    static final int ASK_CONTACTS = 4;

    private PhoneActions() {}

    static String run(Activity a, JSONObject j) {
        try {
            switch (j.optString("action")) {
                case "open_url": {
                    Uri u = Uri.parse(j.optString("url"));
                    if (!"https".equals(u.getScheme()) && !"http".equals(u.getScheme())) return "bad";
                    return start(a, new Intent(Intent.ACTION_VIEW, u));
                }
                case "web_search": {
                    String q = j.optString("query");
                    if (q.isEmpty()) return "bad";
                    String r = start(a, new Intent(Intent.ACTION_WEB_SEARCH).putExtra(SearchManager.QUERY, q));
                    return "ok".equals(r) ? r : start(a, new Intent(Intent.ACTION_VIEW,
                        Uri.parse("https://www.google.com/search?q=" + Uri.encode(q))));
                }
                case "open_app":
                    return openApp(a, j.optString("app"));
                case "alarm":
                    return start(a, new Intent(AlarmClock.ACTION_SET_ALARM)
                        .putExtra(AlarmClock.EXTRA_HOUR, j.getInt("hour"))
                        .putExtra(AlarmClock.EXTRA_MINUTES, j.optInt("minute"))
                        .putExtra(AlarmClock.EXTRA_MESSAGE, j.optString("label", "Aurora"))
                        .putExtra(AlarmClock.EXTRA_SKIP_UI, true));
                case "timer":
                    return start(a, new Intent(AlarmClock.ACTION_SET_TIMER)
                        .putExtra(AlarmClock.EXTRA_LENGTH, j.getInt("seconds"))
                        .putExtra(AlarmClock.EXTRA_MESSAGE, j.optString("label", "Aurora"))
                        .putExtra(AlarmClock.EXTRA_SKIP_UI, true));
                case "calendar": {
                    Intent i = new Intent(Intent.ACTION_INSERT).setData(CalendarContract.Events.CONTENT_URI)
                        .putExtra(CalendarContract.Events.TITLE, j.optString("title"))
                        .putExtra(CalendarContract.EXTRA_EVENT_BEGIN_TIME, j.getLong("begin_ms"))
                        .putExtra(CalendarContract.EXTRA_EVENT_END_TIME, j.optLong("end_ms", j.getLong("begin_ms") + 3600_000L));
                    if (!j.optString("location").isEmpty()) i.putExtra(CalendarContract.Events.EVENT_LOCATION, j.optString("location"));
                    return start(a, i);
                }
                case "navigate":
                    return start(a, new Intent(Intent.ACTION_VIEW, Uri.parse("geo:0,0?q=" + Uri.encode(j.optString("destination")))));
                case "call": {
                    String n = number(a, j);
                    return n.startsWith("!") ? n.substring(1) : start(a, new Intent(Intent.ACTION_DIAL, Uri.parse("tel:" + Uri.encode(n))));
                }
                case "message": {
                    String n = number(a, j);
                    if (n.startsWith("!")) return n.substring(1);
                    if ("whatsapp".equals(j.optString("via"))) return whatsapp(a, n, j.optString("text"));
                    return start(a, new Intent(Intent.ACTION_SENDTO, Uri.parse("smsto:" + Uri.encode(n))).putExtra("sms_body", j.optString("text")));
                }
                default:
                    return "bad";
            }
        } catch (org.json.JSONException e) {
            return "bad";
        }
    }

    // the chat with the message written, straight in WhatsApp (then WhatsApp Business, then whatever opens the link):
    // its link wants the number with the country's code, which a contact saved as «347 …» has not (owner, 2 Nov:
    // «non ha aperto l'app sul cel … con il messaggio pronto»)
    private static String whatsapp(Activity a, String n, String text) {
        String iso = a.getSystemService(TelephonyManager.class).getSimCountryIso();
        if (iso == null || iso.isEmpty()) iso = Locale.getDefault().getCountry();
        String e164 = PhoneNumberUtils.formatNumberToE164(n, iso.toUpperCase(Locale.ROOT));
        Uri u = Uri.parse("https://api.whatsapp.com/send?phone=" + (e164 != null ? e164 : n).replaceAll("[^0-9]", "")
            + "&text=" + Uri.encode(text));
        for (String pkg : new String[] {"com.whatsapp", "com.whatsapp.w4b", null}) {
            Intent i = new Intent(Intent.ACTION_VIEW, u);
            if (pkg != null) i.setPackage(pkg);
            if ("ok".equals(start(a, i))) return "ok";
        }
        return "no_app";
    }

    private static String start(Activity a, Intent i) {
        try {
            a.startActivity(i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            return "ok";
        } catch (ActivityNotFoundException | SecurityException e) {
            return "no_app";
        }
    }

    // an installed app by its name as the launcher shows it (manifest: <queries> for the launchable ones)
    private static String openApp(Activity a, String name) {
        String want = name.trim().toLowerCase(Locale.ROOT);
        if (want.isEmpty()) return "bad";
        PackageManager pm = a.getPackageManager();
        List<ResolveInfo> apps = pm.queryIntentActivities(new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER), 0);
        ResolveInfo best = null;
        for (ResolveInfo r : apps) {
            String label = r.loadLabel(pm).toString().toLowerCase(Locale.ROOT);
            if (label.equals(want)) { best = r; break; }
            if (best == null && label.contains(want)) best = r;
        }
        if (best == null) return "no_app";
        Intent i = pm.getLaunchIntentForPackage(best.activityInfo.packageName);
        return i == null ? "no_app" : start(a, i);
    }

    // the number given, or a contact's by their name (the contacts asked once); "!word" when there is none
    private static String number(Activity a, JSONObject j) {
        String n = j.optString("number").trim();
        if (!n.isEmpty()) return n;
        String who = j.optString("contact").trim();
        if (who.isEmpty()) return "!bad";
        if (a.checkSelfPermission(Manifest.permission.READ_CONTACTS) != PackageManager.PERMISSION_GRANTED) {
            a.runOnUiThread(() -> a.requestPermissions(new String[] {Manifest.permission.READ_CONTACTS}, ASK_CONTACTS));
            return "!need_contacts";
        }
        String[] cols = {ContactsContract.CommonDataKinds.Phone.NUMBER};
        try (Cursor c = a.getContentResolver().query(ContactsContract.CommonDataKinds.Phone.CONTENT_URI, cols,
                ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME + " LIKE ?", new String[] {"%" + who + "%"}, null)) {
            if (c != null && c.moveToFirst()) return c.getString(0);
        }
        return "!no_contact";
    }
}
