// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
package org.aurora.app;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RadialGradient;
import android.graphics.Shader;
import android.graphics.drawable.Drawable;
import android.os.SystemClock;
import android.view.View;

import java.util.ArrayDeque;
import java.util.regex.Pattern;

/**
 * The assistant's screen (owner, 1 Nov: «una schermata minimale come quella di Google… fare scorrere le azioni di quello
 * che sta facendo aurora ma niente parole scritte, solo il classico oscilloscopio… il widget "cervello" come sfondo in
 * filigrana»). The WebUI's brain (brain_gray.js, drawn as res drawable brain by build.py) as a watermark; each step of
 * hers lights its area as the brain widget does (brain.js: the same areas, the same names), a signal runs from the
 * area before; the steps' icons slide along under it; the scope shows who is speaking: the owner in blue, Aurora in
 * her green. Only the names of the steps reach the phone, never what they carry.
 */
final class AssistView extends View {
    // the areas of brain.js: a hub in the figure (x, y on its 1 × 0.715), a colour, an icon
    private static final String[] AREA = {"frontal", "language", "motor", "parietal", "occipital", "temporal", "cerebellum", "stem", "phone"};
    private static final float[][] HUB = {{0.215f, 0.225f}, {0.283f, 0.381f}, {0.459f, 0.137f}, {0.645f, 0.215f},
        {0.879f, 0.371f}, {0.508f, 0.459f}, {0.713f, 0.586f}, {0.576f, 0.645f}, {0.459f, 0.137f}};
    private static final int[] RGB = {0x7AA2FF, 0xBE8CFF, 0xFFAA5A, 0x78E6C8, 0xFF78AA, 0x82D2FF, 0xFAD76E, 0xA0FF8C, 0x5EE6B0};
    private static final String[] ICON = {"🧭", "💬", "🛠️", "✅", "👁️", "📚", "🔧", "🌙", "📱"};
    // an event's name → its area, the first that fits (brain.js MAP)
    private static final Pattern[] MAP = {
        Pattern.compile("^(route|think|question|pivot$|abstain|self|run\\.(alone|start|begin)|lessons)"),
        Pattern.compile("^(translate|pivot\\.back|synthesis|answer|talk)"),
        Pattern.compile("^(agent|approval|forge|change|project|routine|react)"),
        Pattern.compile("^(gate|verify|deduce|grid|read\\.reasoning|custom)"),
        Pattern.compile("^(image|video|attach\\.(image|video)|story|dj)"),
        Pattern.compile("^(retrieval|read\\.(memory|pages|web)|memory|about|acquire|shadow)"),
        Pattern.compile("^(tool|plugin)"),
        Pattern.compile("^(rem|backup|update|sentinel|security|home|health|harvest|calendar|diet|notify|cloudflare)"),
        Pattern.compile("^phone"),
    };
    private static final int HER = 0xFF5EE6B0, OWNER = 0xFF7FB8FF, ICONS = 6;

    private final Drawable brain;
    private final float[] glow = new float[AREA.length];
    private final ArrayDeque<Integer> icons = new ArrayDeque<>();
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG), wave = new Paint(Paint.ANTI_ALIAS_FLAG),
        emoji = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Path line = new Path();
    private volatile float mine, hers;                               // the voices' loudness, 0..1, set by the audio threads
    private float shownMine, shownHers, phase, slide;
    private int last = -1, from = -1;
    private long fired, frame;
    private boolean live;

    AssistView(Context c) {
        super(c);
        brain = c.getDrawable(R.drawable.brain);
        wave.setStyle(Paint.Style.STROKE);
        wave.setStrokeCap(Paint.Cap.ROUND);
        emoji.setTextAlign(Paint.Align.CENTER);
    }

    /** The call is up: the brain wakes from its dim pulse. */
    void live(boolean on) { live = on; }

    void level(boolean her, float v) {
        if (her) hers = Math.max(hers * 0.6f, v); else mine = Math.max(mine * 0.6f, v);
    }

    /** A step of hers, by its name only: its area lights, its icon joins the row. */
    void step(String name) {
        int a = -1;
        for (int i = 0; i < MAP.length && a < 0; i++) if (MAP[i].matcher(name).find()) a = i;
        if (a < 0) return;
        final int area = a;
        post(() -> {
            glow[area] = 1f;
            if (area != last) {
                from = last;
                last = area;
                fired = SystemClock.uptimeMillis();
                icons.addLast(area);
                while (icons.size() > ICONS) icons.removeFirst();
                slide = 1f;
            }
        });
    }

    private int dp(float v) { return (int) (v * getResources().getDisplayMetrics().density); }

    @Override
    protected void onDraw(Canvas c) {
        long now = SystemClock.uptimeMillis();
        float dt = frame == 0 ? 0.016f : Math.min(0.1f, (now - frame) / 1000f);
        frame = now;
        int w = getWidth(), h = getHeight();
        c.drawColor(0xFF0B1020);
        // the brain, a watermark: 92 % of the width, in the upper part
        int bw = (int) (w * 0.92f), bh = (int) (bw * 0.715f), bx = (w - bw) / 2, by = (int) (h * 0.36f) - bh / 2;
        float idle = live ? 0.38f : 0.22f + 0.1f * (float) Math.sin(now / 420.0);
        brain.setBounds(bx, by, bx + bw, by + bh);
        brain.setAlpha((int) (255 * idle));
        brain.draw(c);
        for (int i = 0; i < AREA.length; i++) {
            if (glow[i] < 0.02f) continue;
            float x = bx + HUB[i][0] * bw, y = by + HUB[i][1] / 0.715f * bh, r = bw * (0.08f + 0.1f * glow[i]);
            int col = RGB[i];
            paint.setShader(new RadialGradient(x, y, r, new int[] {(int) (200 * glow[i]) << 24 | col, col & 0xFFFFFF},
                null, Shader.TileMode.CLAMP));
            c.drawCircle(x, y, r, paint);
            glow[i] *= (float) Math.pow(0.35, dt);                    // about a second to fade
        }
        paint.setShader(null);
        float run = (now - fired) / 450f;                              // the signal from the area before, along the synapses
        if (from >= 0 && run < 1f) {
            float x = bx + (HUB[from][0] + (HUB[last][0] - HUB[from][0]) * run) * bw;
            float y = by + (HUB[from][1] + (HUB[last][1] - HUB[from][1]) * run) / 0.715f * bh;
            paint.setColor(0xFF000000 | RGB[last]);
            c.drawCircle(x, y, dp(4), paint);
        }
        // the steps' icons, sliding to the left as a new one comes; the older, the fainter
        emoji.setTextSize(dp(26));
        float gap = dp(46), iy = by + bh + dp(56);
        slide = Math.max(0f, slide - dt * 4f);
        int k = 0, n = icons.size();
        for (int a : icons) {
            float x = w / 2f + (k - (n - 1) / 2f + slide) * gap;
            emoji.setAlpha((int) (255 * (0.35f + 0.65f * (k + 1f) / n)));
            c.drawText(ICON[a], x, iy, emoji);
            k++;
        }
        // the scope: the louder voice draws it, blue the owner's, green hers; a thin calm line in between
        shownMine += (mine - shownMine) * Math.min(1f, dt * 14f);
        shownHers += (hers - shownHers) * Math.min(1f, dt * 14f);
        mine *= (float) Math.pow(0.02, dt);
        hers *= (float) Math.pow(0.02, dt);
        boolean her = shownHers >= shownMine;
        float amp = Math.max(shownHers, shownMine), mid = h * 0.8f, span = h * 0.09f;
        phase += dt * (4f + 10f * amp);
        for (int layer = 0; layer < 3; layer++) {
            line.reset();
            float f = 1.5f + layer * 1.1f, a = amp * span * (1f - layer * 0.28f) + dp(1);
            for (int x = 0; x <= w; x += dp(3)) {
                float u = x / (float) w, env = (float) Math.sin(Math.PI * u);      // quiet at the edges
                float y = mid + a * env * (float) Math.sin(2 * Math.PI * f * u * 2 + phase * (1 + layer * 0.4f));
                if (x == 0) line.moveTo(x, y); else line.lineTo(x, y);
            }
            wave.setStrokeWidth(dp(layer == 0 ? 2.5f : 1.5f));
            wave.setColor((her ? HER : OWNER) & 0xFFFFFF | (int) (255 * (0.9f - layer * 0.3f)) << 24);
            c.drawPath(line, wave);
        }
        if (isAttachedToWindow()) postInvalidateOnAnimation();
    }
}
