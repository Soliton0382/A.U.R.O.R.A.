// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
package org.aurora.app;

import android.content.Context;
import android.media.AudioAttributes;
import android.media.AudioDeviceInfo;
import android.media.AudioFormat;
import android.media.AudioManager;
import android.media.AudioRecord;
import android.media.AudioTrack;
import android.media.MediaRecorder;
import android.media.audiofx.AcousticEchoCanceler;
import android.media.audiofx.NoiseSuppressor;
import android.os.Build;
import android.webkit.CookieManager;

import org.json.JSONObject;

import java.util.concurrent.LinkedBlockingQueue;

/**
 * The call's voice: the microphone to Aurora and Aurora to the earpiece, 16 kHz mono 16-bit both ways over the
 * WebSocket (Ws). Android's own call path does the hard part: the voice-communication source with its echo canceller
 * and noise suppressor, the voice-call stream, the earpiece or the loudspeaker.
 */
final class CallAudio {
    interface Events {
        void line(String who, String text);                         // "heard" (the owner) or "said" (Aurora)
        void ended(String why);
    }

    static final int RATE = 16000, FRAME = 640;                     // 20 ms of 16-bit samples
    private final Context ctx;
    private final String base, id;
    private final Events events;
    private final LinkedBlockingQueue<byte[]> play = new LinkedBlockingQueue<>();
    private volatile boolean running, muted;
    private Ws ws;
    private AudioRecord rec;
    private AudioTrack track;

    CallAudio(Context ctx, String base, String id, Events events) {
        this.ctx = ctx;
        this.base = base;
        this.id = id;
        this.events = events;
    }

    void start() {
        running = true;
        new Thread(this::run, "aurora-call").start();
    }

    void mute(boolean on) { muted = on; }

    void speaker(boolean on) {
        AudioManager am = ctx.getSystemService(AudioManager.class);
        if (Build.VERSION.SDK_INT >= 31) {
            if (!on) { am.clearCommunicationDevice(); return; }
            for (AudioDeviceInfo d : am.getAvailableCommunicationDevices()) {
                if (d.getType() == AudioDeviceInfo.TYPE_BUILTIN_SPEAKER) { am.setCommunicationDevice(d); return; }
            }
        } else {
            am.setSpeakerphoneOn(on);
        }
    }

    void hangup() {
        if (!running) return;
        running = false;
        new Thread(() -> {
            try {
                if (ws != null) ws.sendText("{\"type\":\"hangup\"}");
            } catch (Exception e) {
                // gone already
            }
            if (ws != null) ws.close();
        }).start();
    }

    @SuppressWarnings("MissingPermission")                          // RECORD_AUDIO is asked before a call is answered
    private void run() {
        AudioManager am = ctx.getSystemService(AudioManager.class);
        int oldMode = am.getMode();
        am.setMode(AudioManager.MODE_IN_COMMUNICATION);
        String why = "ok";
        try {
            String url = base + "/v1/aurora/call/" + id + "/audio";
            ws = new Ws(url, CookieManager.getInstance().getCookie(base), "AuroraApp/" + BuildConfig.VERSION + " call");
            int in = Math.max(AudioRecord.getMinBufferSize(RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT), 4 * FRAME);
            rec = new AudioRecord(MediaRecorder.AudioSource.VOICE_COMMUNICATION, RATE, AudioFormat.CHANNEL_IN_MONO,
                                  AudioFormat.ENCODING_PCM_16BIT, in);
            if (AcousticEchoCanceler.isAvailable()) { AcousticEchoCanceler a = AcousticEchoCanceler.create(rec.getAudioSessionId()); if (a != null) a.setEnabled(true); }
            if (NoiseSuppressor.isAvailable()) { NoiseSuppressor n = NoiseSuppressor.create(rec.getAudioSessionId()); if (n != null) n.setEnabled(true); }
            int outSize = Math.max(AudioTrack.getMinBufferSize(RATE, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT), 8 * FRAME);
            track = new AudioTrack.Builder()
                .setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
                .setAudioFormat(new AudioFormat.Builder().setSampleRate(RATE).setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT).build())
                .setBufferSizeInBytes(outSize).setTransferMode(AudioTrack.MODE_STREAM).build();
            track.play();
            rec.startRecording();
            new Thread(this::speak, "aurora-call-play").start();
            new Thread(this::listen, "aurora-call-mic").start();
            ws.read(new Ws.Listener() {
                @Override
                public void text(String s) {
                    try {
                        JSONObject j = new JSONObject(s);
                        String type = j.optString("type");
                        if ("flush".equals(type)) {                  // the owner talks over her: what is queued goes
                            play.clear();
                            track.pause();
                            track.flush();
                            track.play();
                        } else if ("heard".equals(type) || "said".equals(type)) {
                            events.line(type, j.optString("text"));
                        }
                    } catch (Exception e) {
                        // a message this version does not know
                    }
                }

                @Override
                public void binary(byte[] b) { play.offer(b); }
            });
        } catch (Exception e) {
            why = running ? String.valueOf(e.getMessage()) : "ok";
        } finally {
            running = false;
            if (ws != null) ws.close();
            if (rec != null) { try { rec.stop(); } catch (Exception e) { /* not started */ } rec.release(); }
            if (track != null) { try { track.stop(); } catch (Exception e) { /* not started */ } track.release(); }
            play.offer(new byte[0]);                                 // wakes the player so it ends
            if (Build.VERSION.SDK_INT >= 31) am.clearCommunicationDevice();
            am.setMode(oldMode);
            events.ended(why);
        }
    }

    private void listen() {
        byte[] buf = new byte[FRAME];
        while (running) {
            int n = rec.read(buf, 0, FRAME);
            if (n <= 0) continue;
            if (muted) java.util.Arrays.fill(buf, (byte) 0);         // silence, not nothing: her pause detector goes on
            try {
                ws.sendBinary(buf, n);
            } catch (Exception e) {
                return;
            }
        }
    }

    private void speak() {
        while (running) {
            try {
                byte[] b = play.take();
                if (b.length == 0) return;
                track.write(b, 0, b.length);
            } catch (Exception e) {
                return;
            }
        }
    }
}
