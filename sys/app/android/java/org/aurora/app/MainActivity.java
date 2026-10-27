// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
package org.aurora.app;

import android.Manifest;
import android.app.Activity;
import android.app.DownloadManager;
import android.app.NotificationManager;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Insets;
import android.net.Uri;
import android.net.http.SslError;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.PowerManager;
import android.provider.Settings;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.inputmethod.EditorInfo;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.PermissionRequest;
import android.webkit.SslErrorHandler;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

/**
 * Phase 1: Aurora's WebUI in a window of its own. The address is asked once and kept; Aurora's own pages open here,
 * any other link in the browser; the microphone is given only to Aurora's pages; the login is the WebUI's own (a
 * registered device, its cookie kept by the WebView).
 */
public class MainActivity extends Activity {
    static final String PREFS = "aurora", ADDRESS = "address";
    static final String ACTION_SETUP = "org.aurora.app.SETUP";      // the launcher shortcut «Cambia indirizzo»
    static final String VIEW = "view";                               // a notification's page (as the WebUI's ?view=)
    private static final int ASK_MIC = 1, PICK_FILE = 2, ASK_NOTIFY = 3;

    private WebView web;
    private LinearLayout setup, welcome, form;
    private EditText host, port;
    private TextView note;
    private String base;
    private PermissionRequest waiting;                               // the page's mic request, until the user answers
    private ValueCallback<Uri[]> picking;
    private FrameLayout root;
    private View custom;                                             // the page's element in full screen (the player's visualiser)
    private WebChromeClient.CustomViewCallback customDone;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        root = new FrameLayout(this);
        web = new WebView(this);
        root.addView(web, new FrameLayout.LayoutParams(-1, -1));
        root.addView(setup = buildSetup(), new FrameLayout.LayoutParams(-1, -1));
        root.setOnApplyWindowInsetsListener(this::pad);
        setContentView(root);
        configure();
        if (Build.VERSION.SDK_INT >= 33) {
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(0, this::back);
        }
        base = getSharedPreferences(PREFS, MODE_PRIVATE).getString(ADDRESS, null);
        if (base == null || ACTION_SETUP.equals(getIntent().getAction())) showSetup(null);
        else if (getIntent().hasExtra(VIEW)) show(getIntent().getStringExtra(VIEW));
        else if (state == null || web.restoreState(state) == null) open(base);
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (base == null) return;
        LineService.start(this);                                     // idempotent: after a login, the line starts
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED && !getSharedPreferences(PREFS, MODE_PRIVATE).getBoolean("asked_notify", false)) {
            getSharedPreferences(PREFS, MODE_PRIVATE).edit().putBoolean("asked_notify", true).apply();
            requestPermissions(new String[] {Manifest.permission.POST_NOTIFICATIONS}, ASK_NOTIFY);
        } else {
            askBattery();
        }
    }

    // once: Android's battery saver would close the line while the phone sleeps; then, once, the full-screen calls
    @SuppressWarnings("BatteryLife")
    private void askBattery() {
        SharedPreferences p = getSharedPreferences(PREFS, MODE_PRIVATE);
        if (p.getBoolean("asked_battery", false) && Build.VERSION.SDK_INT >= 34 && !p.getBoolean("asked_full", false)
                && !getSystemService(NotificationManager.class).canUseFullScreenIntent()) {
            p.edit().putBoolean("asked_full", true).apply();
            toast(getString(R.string.full_screen));
            try {
                startActivity(new Intent(Settings.ACTION_MANAGE_APP_USE_FULL_SCREEN_INTENT, Uri.parse("package:" + getPackageName())));
            } catch (ActivityNotFoundException e) {
                // a phone without this page: the call rings as a heads-up notification
            }
            return;
        }
        if (p.getBoolean("asked_battery", false)
                || getSystemService(PowerManager.class).isIgnoringBatteryOptimizations(getPackageName())) return;
        p.edit().putBoolean("asked_battery", true).apply();
        try {
            startActivity(new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:" + getPackageName())));
        } catch (ActivityNotFoundException e) {
            // a phone without the dialog: the line works while Android lets it
        }
    }

    // a notification's page: the WebUI already open switches page as with a push (its service worker's message);
    // otherwise it opens there
    private void show(String view) {
        hideSetup();
        String url = web.getUrl();
        if (url != null && Address.inside(base, url)) {
            web.evaluateJavascript("navigator.serviceWorker&&navigator.serviceWorker.dispatchEvent(new MessageEvent('message',"
                + "{data:{type:'show',view:" + JSONObject.quote(view) + "}}))", null);
        } else {
            web.loadUrl(base + "/?view=" + Uri.encode(view));
        }
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        if (ACTION_SETUP.equals(intent.getAction())) showSetup(null);
        else if (intent.hasExtra(VIEW) && base != null) show(intent.getStringExtra(VIEW));
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        web.saveState(out);
    }

    @Override
    protected void onPause() {
        super.onPause();
        CookieManager.getInstance().flush();                         // the device's login survives a killed app
    }

    // the window under the status bar and above the keyboard (edge to edge is forced from Android 15)
    private WindowInsets pad(View v, WindowInsets in) {
        if (custom != null) {                                        // full screen: edge to edge, no bars
            v.setPadding(0, 0, 0, 0);
            return in;
        }
        if (Build.VERSION.SDK_INT >= 30) {
            Insets i = in.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.ime());
            v.setPadding(i.left, i.top, i.right, i.bottom);
        } else {
            v.setPadding(in.getSystemWindowInsetLeft(), in.getSystemWindowInsetTop(),
                         in.getSystemWindowInsetRight(), in.getSystemWindowInsetBottom());
        }
        return in;
    }

    private void back() {
        if (custom != null) { exitFull(); return; }
        if (setup.getVisibility() == View.VISIBLE && base != null) hideSetup();
        else if (web.canGoBack()) web.goBack();
        else moveTaskToBack(true);                                   // like leaving an app: Aurora stays where she was
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() { back(); }

    // ---- welcome and address: «Inizia», then the address and the port, then «Connetti» --------------------------
    private LinearLayout panel() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setGravity(Gravity.CENTER);
        int p = (int) (24 * getResources().getDisplayMetrics().density);
        box.setPadding(p, p, p, p);
        return box;
    }

    private TextView text(int id, float size, int color) {
        TextView t = new TextView(this);
        t.setText(id);
        t.setTextSize(size);
        t.setTextColor(color);
        t.setPadding(0, 12, 0, 12);
        return t;
    }

    private EditText input(int hint, int type) {
        EditText e = new EditText(this);
        e.setHint(hint);
        e.setTextColor(0xFFE8ECF8);
        e.setHintTextColor(0xFF7A8299);
        e.setSingleLine(true);
        e.setInputType(type);
        return e;
    }

    private LinearLayout buildSetup() {
        FrameLayout both = new FrameLayout(this);
        welcome = panel();
        welcome.addView(text(R.string.app_name, 34, 0xFF5EE6B0));
        welcome.addView(text(R.string.welcome_text, 16, 0xFFE8ECF8));
        Button start = new Button(this);
        start.setText(R.string.start);
        start.setOnClickListener(v -> { welcome.setVisibility(View.GONE); form.setVisibility(View.VISIBLE); });
        welcome.addView(start);
        form = panel();
        form.addView(text(R.string.setup_title, 22, 0xFFE8ECF8));
        form.addView(text(R.string.host_label, 14, 0xFFA9B1C7));
        form.addView(host = input(R.string.host_hint, InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI),
                     new LinearLayout.LayoutParams(-1, -2));
        form.addView(text(R.string.port_label, 14, 0xFFA9B1C7));
        form.addView(port = input(R.string.port_hint, InputType.TYPE_CLASS_NUMBER), new LinearLayout.LayoutParams(-1, -2));
        port.setImeOptions(EditorInfo.IME_ACTION_GO);
        port.setOnEditorActionListener((v, id, ev) -> { save(); return true; });
        form.addView(note = text(R.string.setup_help, 14, 0xFFA9B1C7));
        Button go = new Button(this);
        go.setText(R.string.setup_go);
        go.setOnClickListener(v -> save());
        form.addView(go);
        both.addView(welcome, new FrameLayout.LayoutParams(-1, -1));
        both.addView(form, new FrameLayout.LayoutParams(-1, -1));
        LinearLayout box = new LinearLayout(this);
        box.setBackgroundColor(getColor(R.color.night));
        box.addView(both, new LinearLayout.LayoutParams(-1, -1));
        return box;
    }

    // the first time the welcome; after an error or from the shortcut, straight to the address, filled in
    private void showSetup(String why) {
        boolean first = base == null && why == null;
        welcome.setVisibility(first ? View.VISIBLE : View.GONE);
        form.setVisibility(first ? View.GONE : View.VISIBLE);
        Uri u = base == null ? null : Uri.parse(base);
        host.setText(u == null ? "" : u.getHost());
        port.setText(u == null || u.getPort() < 0 ? "" : String.valueOf(u.getPort()));
        note.setText(why == null ? getString(R.string.setup_help) : why);
        setup.setVisibility(View.VISIBLE);
    }

    private void hideSetup() { setup.setVisibility(View.GONE); }

    private void save() {
        String a = Address.of(host.getText().toString(), port.getText().toString());
        if (a == null) { note.setText(R.string.bad_address); return; }
        getSharedPreferences(PREFS, MODE_PRIVATE).edit().putString(ADDRESS, a).apply();
        base = a;
        open(a);
    }

    private void open(String a) {
        hideSetup();
        web.loadUrl(a + "/");
    }

    // ---- the WebView ----------------------------------------------------------------------------------------------
    private void configure() {
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);               // Aurora's voice answers without a second tap
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setUserAgentString(s.getUserAgentString() + " AuroraApp/" + BuildConfig.VERSION);
        CookieManager.getInstance().setAcceptCookie(true);
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) {
                String url = r.getUrl().toString();
                if (Address.inside(base, url)) return false;
                outside(r.getUrl());
                return true;
            }

            @Override
            public void onPageFinished(WebView v, String url) {
                // the first time too, right after «Connetti» and the login: the line needs the device's cookie
                if (Address.inside(base, url)) {
                    CookieManager.getInstance().flush();
                    LineService.start(MainActivity.this);
                }
            }

            @Override
            public void onReceivedError(WebView v, WebResourceRequest r, WebResourceError e) {
                if (r.isForMainFrame()) showSetup(getString(R.string.unreachable, e.getDescription()));
            }

            @Override
            public void onReceivedSslError(WebView v, SslErrorHandler h, SslError e) {
                h.cancel();                                          // never accepted silently
                showSetup(getString(R.string.untrusted));
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(PermissionRequest r) { runOnUiThread(() -> answer(r)); }

            // the page's full screen (the player's visualiser; owner, 27 Oct: «aggiornare l'app android per avere la
            // giusta integrazione tutto schermo»): its element over everything, the system bars hidden, immersive
            @Override
            public void onShowCustomView(View v, CustomViewCallback cb) { runOnUiThread(() -> enterFull(v, cb)); }

            @Override
            public void onHideCustomView() { runOnUiThread(MainActivity.this::exitFull); }

            @Override
            public boolean onShowFileChooser(WebView v, ValueCallback<Uri[]> cb, FileChooserParams p) {
                if (picking != null) picking.onReceiveValue(null);
                picking = cb;
                try {
                    startActivityForResult(p.createIntent(), PICK_FILE);
                } catch (ActivityNotFoundException e) {
                    picking = null;
                    toast(getString(R.string.no_app));
                    return false;
                }
                return true;
            }
        });
        web.setDownloadListener((url, agent, disposition, mime, length) -> download(url, agent, disposition, mime));
        web.addJavascriptInterface(new Bridge(), "AuroraApp");
    }

    private void enterFull(View v, WebChromeClient.CustomViewCallback cb) {
        if (custom != null) { cb.onCustomViewHidden(); return; }
        custom = v;
        customDone = cb;
        root.addView(v, new FrameLayout.LayoutParams(-1, -1));
        immersive(true);
        root.requestApplyInsets();
    }

    private void exitFull() {
        if (custom == null) return;
        root.removeView(custom);
        custom = null;
        immersive(false);
        if (customDone != null) customDone.onCustomViewHidden();
        customDone = null;
        root.requestApplyInsets();
    }

    @SuppressWarnings("deprecation")
    private void immersive(boolean on) {
        if (Build.VERSION.SDK_INT >= 30) {
            WindowInsetsController c = getWindow().getInsetsController();
            if (c == null) return;
            if (on) {
                c.setSystemBarsBehavior(WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
                c.hide(WindowInsets.Type.systemBars());
            } else {
                c.show(WindowInsets.Type.systemBars());
            }
        } else {                                                     // Android 10: the flags of before
            getWindow().getDecorView().setSystemUiVisibility(on
                ? View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY | View.SYSTEM_UI_FLAG_FULLSCREEN | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                  | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                : View.SYSTEM_UI_FLAG_VISIBLE);
        }
    }

    /** What the WebUI asks the app: two answers about the notifications (push.js), and calling Aurora (chat.js). */
    final class Bridge {
        @JavascriptInterface
        public boolean notifications() {
            return getSystemService(NotificationManager.class).areNotificationsEnabled();
        }

        @JavascriptInterface
        public void settings() {
            runOnUiThread(() -> startActivity(new Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                .putExtra(Settings.EXTRA_APP_PACKAGE, getPackageName())));
        }

        /** 📞 The owner calls Aurora: the call Aurora made ready (POST /v1/aurora/call/dial), opened already answered. */
        @JavascriptInterface
        public void callAurora(String id) {
            if (id == null || !id.matches("[0-9a-f]{16}")) return;
            runOnUiThread(() -> startActivity(new Intent(MainActivity.this, CallActivity.class).setAction(CallActivity.ANSWER)
                .putExtra(CallActivity.ID, id).putExtra(CallActivity.REASON, getString(R.string.call_out))));
        }
    }

    private void outside(Uri u) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, u));
        } catch (ActivityNotFoundException e) {
            toast(getString(R.string.no_app));
        }
    }

    // only Aurora's own pages get the microphone, and only the microphone
    private void answer(PermissionRequest r) {
        boolean audio = false;
        for (String res : r.getResources()) audio |= PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(res);
        if (!audio || !Address.inside(base, r.getOrigin().toString())) { r.deny(); return; }
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
            r.grant(new String[] {PermissionRequest.RESOURCE_AUDIO_CAPTURE});
            return;
        }
        if (waiting != null) waiting.deny();
        waiting = r;
        requestPermissions(new String[] {Manifest.permission.RECORD_AUDIO}, ASK_MIC);
    }

    @Override
    public void onRequestPermissionsResult(int code, String[] perms, int[] results) {
        if (code == ASK_NOTIFY) { askBattery(); return; }
        if (code != ASK_MIC || waiting == null) return;
        if (results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED) {
            waiting.grant(new String[] {PermissionRequest.RESOURCE_AUDIO_CAPTURE});
        } else {
            waiting.deny();
            toast(getString(R.string.mic_denied));
        }
        waiting = null;
    }

    @Override
    protected void onActivityResult(int code, int result, Intent data) {
        if (code == PICK_FILE && picking != null) {
            picking.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(result, data));
            picking = null;
        }
    }

    // a file from Aurora: fetched by the system's downloader with the device's login, saved in Downloads
    private void download(String url, String agent, String disposition, String mime) {
        if (!Address.inside(base, url)) { outside(Uri.parse(url)); return; }
        String name = URLUtil.guessFileName(url, disposition, mime);
        DownloadManager.Request q = new DownloadManager.Request(Uri.parse(url));
        q.addRequestHeader("Cookie", CookieManager.getInstance().getCookie(url));
        q.addRequestHeader("User-Agent", agent);
        q.setMimeType(mime);
        q.setTitle(name);
        q.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
        q.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, name);
        ((DownloadManager) getSystemService(DOWNLOAD_SERVICE)).enqueue(q);
        toast(getString(R.string.download, name));
    }

    private void toast(String s) { Toast.makeText(this, s, Toast.LENGTH_LONG).show(); }
}
