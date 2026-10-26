// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
package org.aurora.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Person;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ServiceInfo;
import android.media.AudioAttributes;
import android.media.RingtoneManager;
import android.os.Build;
import android.os.IBinder;
import android.webkit.CookieManager;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;

/**
 * Phase 2, the line: a request kept open towards Aurora (GET /v1/aurora/line, up to 50 s, then again), with the
 * device's login. What comes back is shown as a notification: no push service in between. A foreground service, so
 * Android keeps it alive; it starts with the app and at boot, and stops when Aurora says the login is gone.
 */
public class LineService extends Service {
    static final String LINE = "line", NEWS = "news", CALLS = "calls", AFTER = "after";
    private static final int ONGOING = 1, WAIT = 50;
    private volatile boolean running;
    private Thread loop;

    static void start(Context c) {
        if (c.getSharedPreferences(MainActivity.PREFS, MODE_PRIVATE).getString(MainActivity.ADDRESS, null) == null) return;
        try {
            c.startForegroundService(new Intent(c, LineService.class));
        } catch (RuntimeException e) {
            // not allowed from the background right now: the next opening of the app starts it
        }
    }

    @Override
    public void onCreate() {
        super.onCreate();
        NotificationManager nm = getSystemService(NotificationManager.class);
        nm.createNotificationChannel(new NotificationChannel(LINE, getString(R.string.ch_line), NotificationManager.IMPORTANCE_MIN));
        NotificationChannel news = new NotificationChannel(NEWS, getString(R.string.ch_news), NotificationManager.IMPORTANCE_HIGH);
        news.enableVibration(true);
        nm.createNotificationChannel(news);
        NotificationChannel calls = new NotificationChannel(CALLS, getString(R.string.ch_calls), NotificationManager.IMPORTANCE_HIGH);
        calls.setSound(RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE), new AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_NOTIFICATION_RINGTONE).setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build());
        calls.enableVibration(true);
        calls.setVibrationPattern(new long[] {0, 1000, 1000});
        nm.createNotificationChannel(calls);
        Notification on = new Notification.Builder(this, LINE).setSmallIcon(R.drawable.ic_aurora)
            .setContentTitle(getString(R.string.line_on)).setContentIntent(open(null)).setOngoing(true).build();
        if (Build.VERSION.SDK_INT >= 34) startForeground(ONGOING, on, ServiceInfo.FOREGROUND_SERVICE_TYPE_REMOTE_MESSAGING);
        else startForeground(ONGOING, on);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int id) {
        if (loop == null || !loop.isAlive()) {
            running = true;
            loop = new Thread(this::listen, "aurora-line");
            loop.start();
        }
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        running = false;
        if (loop != null) loop.interrupt();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent i) { return null; }

    private void listen() {
        SharedPreferences p = getSharedPreferences(MainActivity.PREFS, MODE_PRIVATE);
        long backoff = 2000;
        while (running) {
            String base = p.getString(MainActivity.ADDRESS, null), after = p.getString(AFTER, "");
            if (base == null) break;
            try {
                String q = after.isEmpty() ? "" : "?after=" + URLEncoder.encode(after, "UTF-8") + "&wait=" + WAIT;
                JSONObject r = get(base + "/v1/aurora/line" + q);
                JSONArray ev = r.optJSONArray("events");
                for (int i = 0; ev != null && i < ev.length(); i++) show(ev.getJSONObject(i));
                p.edit().putString(AFTER, r.optString("next", after)).apply();   // what was shown is acknowledged
                backoff = 2000;
            } catch (Gone e) {
                break;                                                    // logged out: the app opened again restarts it
            } catch (Exception e) {
                try {
                    Thread.sleep(backoff);
                } catch (InterruptedException stop) {
                    break;
                }
                backoff = Math.min(backoff * 2, 60000);
            }
        }
        stopSelf();
    }

    private static final class Gone extends IOException {}

    private JSONObject get(String url) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        try {
            c.setConnectTimeout(15000);
            c.setReadTimeout((WAIT + 20) * 1000);
            String cookie = CookieManager.getInstance().getCookie(url);
            if (cookie != null) c.setRequestProperty("Cookie", cookie);
            c.setRequestProperty("User-Agent", "AuroraApp/" + BuildConfig.VERSION + " line");
            int code = c.getResponseCode();
            if (code == 401 || code == 403) throw new Gone();
            if (code != 200) throw new IOException("HTTP " + code);
            try (InputStream in = c.getInputStream()) {
                ByteArrayOutputStream b = new ByteArrayOutputStream();
                byte[] buf = new byte[8192];
                for (int n; (n = in.read(buf)) > 0; ) b.write(buf, 0, n);
                return new JSONObject(b.toString("UTF-8"));
            }
        } finally {
            c.disconnect();
        }
    }

    private void show(JSONObject e) {
        String kind = e.optString("kind");
        if ("call".equals(kind)) {
            if (System.currentTimeMillis() / 1000.0 - e.optDouble("at", 0) < e.optInt("ring", 30)) ring(e);
            return;                                                  // an old call (the phone was offline): its end tells
        }
        if ("call_answered".equals(kind)) {                         // answered on another phone: this one stops
            CallActivity.stopRinging(this, e.optString("call"));
            CallActivity.over(e.optString("call"));
            return;
        }
        if ("call_end".equals(kind)) {
            CallActivity.stopRinging(this, e.optString("call"));
            CallActivity.over(e.optString("call"));
        }
        String tag = e.optString("tag", "aurora");
        Notification n = new Notification.Builder(this, NEWS).setSmallIcon(R.drawable.ic_aurora)
            .setContentTitle(e.optString("title", "Aurora")).setContentText(e.optString("body", ""))
            .setStyle(new Notification.BigTextStyle().bigText(e.optString("body", "")))
            .setContentIntent(open(e.optString("view", "chat"))).setAutoCancel(true).build();
        getSystemService(NotificationManager.class).notify(tag, 0, n);   // same tag: the newer replaces the older
    }

    // Aurora calls: a ringing call over the lock screen (full-screen intent), «Rispondi» / «Rifiuta» on the notification
    private void ring(JSONObject e) {
        String id = e.optString("call"), reason = e.optString("body");
        Intent full = new Intent(this, CallActivity.class).putExtra(CallActivity.ID, id).putExtra(CallActivity.REASON, reason)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_NO_USER_ACTION);
        int flags = PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT;
        PendingIntent show = PendingIntent.getActivity(this, id.hashCode(), full, flags);
        PendingIntent answer = PendingIntent.getActivity(this, id.hashCode() + 1,
            new Intent(full).setAction(CallActivity.ANSWER), flags);
        PendingIntent decline = PendingIntent.getBroadcast(this, id.hashCode() + 2,
            new Intent(this, CallDecline.class).putExtra(CallActivity.ID, id), flags);
        Notification.Builder b = new Notification.Builder(this, CALLS).setSmallIcon(R.drawable.ic_aurora)
            .setContentTitle(getString(R.string.call_title)).setContentText(reason)
            .setCategory(Notification.CATEGORY_CALL).setFullScreenIntent(show, true).setContentIntent(show)
            .setOngoing(true).setTimeoutAfter(e.optInt("ring", 30) * 1000L);
        if (Build.VERSION.SDK_INT >= 31) {
            b.setStyle(Notification.CallStyle.forIncomingCall(
                new Person.Builder().setName(getString(R.string.app_name)).setImportant(true).build(), decline, answer));
        } else {
            b.addAction(new Notification.Action.Builder(null, getString(R.string.call_decline), decline).build());
            b.addAction(new Notification.Action.Builder(null, getString(R.string.call_answer), answer).build());
        }
        Notification n = b.build();
        n.flags |= Notification.FLAG_INSISTENT;                      // the ringtone goes on until answered or over
        getSystemService(NotificationManager.class).notify(CallActivity.RING_TAG, id.hashCode(), n);
    }

    private PendingIntent open(String view) {
        Intent i = new Intent(this, MainActivity.class).setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        if (view != null) i.putExtra(MainActivity.VIEW, view);
        return PendingIntent.getActivity(this, view == null ? 0 : view.hashCode(), i,
                                         PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
    }
}
