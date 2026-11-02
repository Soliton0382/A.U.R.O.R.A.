// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
package org.aurora.app;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.WindowManager;
import android.webkit.CookieManager;
import android.widget.FrameLayout;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.Set;

/**
 * Aurora as the phone's assistant (N68; owner, 1 Nov: «gestire aurora assistente come se fosse una chiamata ad aurora
 * ma con la gestione delle azioni cellulare»; 2 Nov: «se apro l'assistente si vede il full screen dell'assistente»).
 * The call the 📞 makes (POST /v1/aurora/call/dial, then CallAudio), opened straight from the long press with no page
 * to load, on the loudspeaker, on its own screen (AssistView): no words, the brain and the scope. An action that hands
 * the screen to another app (YouTube, the maps, WhatsApp) ends the call once she has said so; a timer or an alarm
 * leaves it open. Not paired yet (no device cookie): the app opens, for its login.
 */
public class AssistActivity extends Activity implements CallAudio.Events {
    private static final int ASK_MIC = 1;
    private static final Set<String> TAKEOVER = Set.of("open_app", "open_url", "web_search", "navigate", "call", "message", "calendar");
    private final Handler ui = new Handler(Looper.getMainLooper());
    private AssistView view;
    private CallAudio audio;
    private String base;
    private boolean closing;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        base = getSharedPreferences(MainActivity.PREFS, MODE_PRIVATE).getString(MainActivity.ADDRESS, null);
        if (base == null || CookieManager.getInstance().getCookie(base) == null) { app(); return; }
        FrameLayout root = new FrameLayout(this);
        root.addView(view = new AssistView(this), new FrameLayout.LayoutParams(-1, -1));
        TextView close = new TextView(this);                         // the only control: ✕, as back does
        close.setText("✕");
        close.setTextSize(22);
        close.setTextColor(0xFFA9B1C7);
        close.setGravity(Gravity.CENTER);
        GradientDrawable g = new GradientDrawable();
        g.setShape(GradientDrawable.OVAL);
        g.setColor(0xFF1A2140);
        close.setBackground(g);
        close.setOnClickListener(v -> close());
        int s = (int) (64 * getResources().getDisplayMetrics().density);
        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(s, s, Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL);
        lp.bottomMargin = s / 2;
        root.addView(close, lp);
        setContentView(root);
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[] {Manifest.permission.RECORD_AUDIO}, ASK_MIC);
        } else {
            dial();
        }
    }

    // the WebUI, for its login or a new address: the assistant needs the device's cookie
    private void app() {
        startActivity(new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        finish();
    }

    private void dial() {
        new Thread(() -> {
            int code = 0;
            String id = null;
            try {
                HttpURLConnection h = (HttpURLConnection) new URL(base + "/v1/aurora/call/dial?as=assistant").openConnection();
                h.setRequestMethod("POST");
                h.setConnectTimeout(8000);
                h.setReadTimeout(8000);
                h.setRequestProperty("Cookie", CookieManager.getInstance().getCookie(base));
                h.setRequestProperty("User-Agent", "AuroraApp/" + BuildConfig.VERSION + " assistant");
                code = h.getResponseCode();
                if (code == 200) {
                    try (InputStream in = h.getInputStream()) {
                        ByteArrayOutputStream out = new ByteArrayOutputStream();
                        byte[] buf = new byte[4096];
                        for (int n; (n = in.read(buf)) > 0; ) out.write(buf, 0, n);
                        id = new JSONObject(out.toString("UTF-8")).optString("id", null);
                    }
                }
                h.disconnect();
            } catch (Exception e) {
                // offline or not trusted: said below
            }
            final int got = code;
            final String call = id;
            runOnUiThread(() -> {
                if (isFinishing()) return;
                if (got == 401 || got == 403) { app(); return; }        // the login is gone: the app asks for it again
                if (call == null || !call.matches("[0-9a-f]{16}")) {
                    Toast.makeText(this, getString(R.string.unreachable, base), Toast.LENGTH_LONG).show();
                    finish();
                    return;
                }
                audio = new CallAudio(getApplicationContext(), base, call, this);
                audio.start();
                audio.speaker(true);                                 // the assistant is spoken to, not held at the ear
                view.live(true);
            });
        }, "aurora-assist-dial").start();
    }

    private void close() {
        closing = true;
        if (audio != null) audio.hangup(); else finish();
    }

    @Override
    public void line(String who, String text) {}                    // no words on this screen

    @Override
    public void step(String name) { view.step(name); }

    @Override
    public void level(boolean her, float v) { view.level(her, v); }

    @Override
    public void phone(JSONObject action) {
        runOnUiThread(() -> {
            String r = PhoneActions.run(this, action);
            view.step("phone");
            CallAudio a = audio;
            if (a == null) return;
            a.phoneResult(action.optString("id"), r);
            if ("ok".equals(r) && TAKEOVER.contains(action.optString("action"))) ui.postDelayed(() -> {
                if (audio != null) audio.hangup();                   // «Fatto.» said: the other app has the screen
            }, 1800);
        });
    }

    @Override
    public void ended(String why) {
        runOnUiThread(() -> {
            audio = null;
            if (!closing && !"ok".equals(why)) Toast.makeText(this, getString(R.string.call_failed, why), Toast.LENGTH_LONG).show();
            finish();
        });
    }

    @Override
    public void onRequestPermissionsResult(int code, String[] perms, int[] res) {
        boolean ok = res.length > 0 && res[0] == PackageManager.PERMISSION_GRANTED;
        if (code == ASK_MIC) {
            if (ok) dial();
            else { Toast.makeText(this, R.string.mic_denied, Toast.LENGTH_LONG).show(); finish(); }
        } else if (code == PhoneActions.ASK_CONTACTS) {
            Toast.makeText(this, ok ? R.string.contacts_ok : R.string.contacts_denied, Toast.LENGTH_LONG).show();
        }
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() { close(); }

    @Override
    protected void onDestroy() {
        if (audio != null) audio.hangup();
        super.onDestroy();
    }
}
