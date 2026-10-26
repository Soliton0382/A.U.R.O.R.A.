// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
package org.aurora.app;

import android.Manifest;
import android.app.Activity;
import android.app.NotificationManager;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.webkit.CookieManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.net.HttpURLConnection;
import java.net.URL;

/**
 * Aurora calling: the classic call screen (owner, 25 Oct), over the lock screen. Ringing: «Rifiuta» / «Rispondi». In the
 * call: the time, what each one said, mute, loudspeaker, hang up; the screen goes dark at the ear (proximity).
 */
public class CallActivity extends Activity implements CallAudio.Events {
    static final String ID = "call", REASON = "reason", ANSWER = "org.aurora.app.ANSWER";
    static final String RING_TAG = "call";
    private static final int ASK_MIC = 1;
    static volatile CallActivity current;                           // the line ends a call that stopped ringing

    private String id, base;
    private TextView state, said, heard;
    private LinearLayout buttons;
    private CallAudio audio;
    private PowerManager.WakeLock ear;
    private long since;
    private boolean muted, loud;
    private final Handler ui = new Handler(Looper.getMainLooper());

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        setShowWhenLocked(true);
        setTurnScreenOn(true);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        id = getIntent().getStringExtra(ID);
        base = getSharedPreferences(MainActivity.PREFS, MODE_PRIVATE).getString(MainActivity.ADDRESS, null);
        if (id == null || base == null) { finish(); return; }
        current = this;
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER_HORIZONTAL);
        root.setBackgroundColor(getColor(R.color.night));
        int p = dp(28);
        root.setPadding(p, dp(90), p, dp(56));
        root.addView(text(getString(R.string.app_name), 40, 0xFF5EE6B0));
        root.addView(text(getIntent().getStringExtra(REASON), 18, 0xFFE8ECF8));
        root.addView(state = text(getString(R.string.call_ringing), 16, 0xFFA9B1C7));
        LinearLayout talk = new LinearLayout(this);
        talk.setOrientation(LinearLayout.VERTICAL);
        talk.addView(heard = text("", 15, 0xFF7FB8FF));
        talk.addView(said = text("", 15, 0xFFE8ECF8));
        root.addView(talk, new LinearLayout.LayoutParams(-1, 0, 1));
        buttons = new LinearLayout(this);
        buttons.setGravity(Gravity.CENTER);
        root.addView(buttons, new LinearLayout.LayoutParams(-1, -2));
        setContentView(root);
        if (ANSWER.equals(getIntent().getAction())) answer();
        else ringing();
    }

    @Override
    protected void onNewIntent(Intent i) {
        super.onNewIntent(i);
        if (ANSWER.equals(i.getAction()) && audio == null && id.equals(i.getStringExtra(ID))) answer();
    }

    private int dp(int v) { return (int) (v * getResources().getDisplayMetrics().density); }

    private TextView text(String s, float size, int color) {
        TextView t = new TextView(this);
        t.setText(s == null ? "" : s);
        t.setTextSize(size);
        t.setTextColor(color);
        t.setGravity(Gravity.CENTER);
        t.setPadding(0, dp(8), 0, dp(8));
        return t;
    }

    private Button round(String label, int color, View.OnClickListener l) {
        Button b = new Button(this);
        b.setText(label);
        b.setTextColor(0xFFFFFFFF);
        b.setTextSize(15);
        GradientDrawable g = new GradientDrawable();
        g.setShape(GradientDrawable.OVAL);
        g.setColor(color);
        b.setBackground(g);
        b.setOnClickListener(l);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(dp(92), dp(92));
        lp.setMargins(dp(14), 0, dp(14), 0);
        b.setLayoutParams(lp);
        return b;
    }

    private void ringing() {
        buttons.removeAllViews();
        buttons.addView(round(getString(R.string.call_decline), 0xFFE5484D, v -> decline()));
        buttons.addView(round(getString(R.string.call_answer), 0xFF30A46C, v -> answer()));
    }

    private void incall() {
        buttons.removeAllViews();
        Button mute = round(getString(R.string.call_mute), 0xFF3A4260, null);
        mute.setOnClickListener(v -> { muted = !muted; audio.mute(muted); mute.setAlpha(muted ? 1f : 0.6f); });
        mute.setAlpha(0.6f);
        Button spk = round(getString(R.string.call_speaker), 0xFF3A4260, null);
        spk.setOnClickListener(v -> { loud = !loud; audio.speaker(loud); spk.setAlpha(loud ? 1f : 0.6f); });
        spk.setAlpha(0.6f);
        buttons.addView(mute);
        buttons.addView(round(getString(R.string.call_hangup), 0xFFE5484D, v -> audio.hangup()));
        buttons.addView(spk);
    }

    static void stopRinging(Context c, String id) {
        c.getSystemService(NotificationManager.class).cancel(RING_TAG, id.hashCode());
    }

    private void answer() {
        if (audio != null) return;
        stopRinging(this, id);
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[] {Manifest.permission.RECORD_AUDIO}, ASK_MIC);
            return;
        }
        state.setText(R.string.call_connecting);
        audio = new CallAudio(getApplicationContext(), base, id, this);
        audio.start();
        since = System.currentTimeMillis();
        PowerManager pm = getSystemService(PowerManager.class);
        if (pm.isWakeLockLevelSupported(PowerManager.PROXIMITY_SCREEN_OFF_WAKE_LOCK)) {
            ear = pm.newWakeLock(PowerManager.PROXIMITY_SCREEN_OFF_WAKE_LOCK, "aurora:call");
            ear.acquire(2 * 60 * 60 * 1000L);
        }
        incall();
        tick();
    }

    private void tick() {
        if (audio == null || isFinishing()) return;
        long s = (System.currentTimeMillis() - since) / 1000;
        state.setText(getString(R.string.call_in, s / 60, s % 60));
        ui.postDelayed(this::tick, 1000);
    }

    @Override
    public void onRequestPermissionsResult(int code, String[] perms, int[] res) {
        if (code != ASK_MIC) return;
        if (res.length > 0 && res[0] == PackageManager.PERMISSION_GRANTED) answer();
        else decline();
    }

    private void decline() {
        stopRinging(this, id);
        decline(this, base, id);
        finish();
    }

    /** Tells Aurora the call was declined: she leaves its reason as a notification. */
    static void decline(Context c, String base, String id) {
        new Thread(() -> {
            try {
                HttpURLConnection h = (HttpURLConnection) new URL(base + "/v1/aurora/call/" + id + "/decline").openConnection();
                h.setRequestMethod("POST");
                h.setConnectTimeout(10000);
                h.setReadTimeout(10000);
                String cookie = CookieManager.getInstance().getCookie(base);
                if (cookie != null) h.setRequestProperty("Cookie", cookie);
                h.getResponseCode();
                h.disconnect();
            } catch (Exception e) {
                // offline: the call becomes a missed one on Aurora's side
            }
        }).start();
    }

    /** The line says the call is over (missed, declined elsewhere): a ringing screen goes away. */
    static void over(String id) {
        CallActivity a = current;
        if (a != null && id.equals(a.id) && a.audio == null) a.runOnUiThread(a::finish);
    }

    @Override
    public void line(String who, String text) {
        runOnUiThread(() -> ("heard".equals(who) ? heard : said).setText(("heard".equals(who) ? "🗣️ " : "✨ ") + text));
    }

    @Override
    public void ended(String why) {
        runOnUiThread(() -> {
            if (ear != null && ear.isHeld()) ear.release();
            audio = null;
            state.setText("ok".equals(why) ? getString(R.string.call_over) : getString(R.string.call_failed, why));
            buttons.removeAllViews();
            ui.postDelayed(this::finish, "ok".equals(why) ? 1500 : 5000);
        });
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        if (audio == null) super.onBackPressed();                    // in a call, back does not drop it
    }

    @Override
    protected void onDestroy() {
        if (current == this) current = null;
        if (audio != null) audio.hangup();
        if (ear != null && ear.isHeld()) ear.release();
        super.onDestroy();
    }
}
