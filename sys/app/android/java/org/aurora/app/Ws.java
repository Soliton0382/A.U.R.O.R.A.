// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
package org.aurora.app;

import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Base64;

import javax.net.ssl.HttpsURLConnection;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;

/**
 * A WebSocket client (RFC 6455) over TLS, just what the call needs: Android has none of its own. The certificate is
 * checked by the system (and the app's network security config), the host name by the HTTPS verifier; the device's
 * cookie goes with the handshake. One thread reads (read), any thread writes (send* are synchronized).
 */
final class Ws {
    interface Listener {
        void text(String s);
        void binary(byte[] b);
    }

    private static final SecureRandom RNG = new SecureRandom();
    private final SSLSocket socket;
    private final OutputStream out;
    private final DataInputStream in;
    private volatile boolean closed;

    Ws(String url, String cookie, String agent) throws IOException {
        URI u = URI.create(url.replaceFirst("^https", "wss"));
        int port = u.getPort() > 0 ? u.getPort() : 443;
        socket = (SSLSocket) SSLSocketFactory.getDefault().createSocket();
        socket.connect(new InetSocketAddress(u.getHost(), port), 15000);
        socket.startHandshake();
        if (!HttpsURLConnection.getDefaultHostnameVerifier().verify(u.getHost(), socket.getSession())) {
            socket.close();
            throw new IOException("certificate not for " + u.getHost());
        }
        socket.setTcpNoDelay(true);                                  // 20 ms frames: no waiting to fill a packet
        out = socket.getOutputStream();
        in = new DataInputStream(socket.getInputStream());
        byte[] nonce = new byte[16];
        RNG.nextBytes(nonce);
        String host = u.getHost() + (port == 443 ? "" : ":" + port);
        String req = "GET " + u.getRawPath() + " HTTP/1.1\r\nHost: " + host + "\r\nUpgrade: websocket\r\n"
            + "Connection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: "
            + Base64.getEncoder().encodeToString(nonce) + "\r\nUser-Agent: " + agent + "\r\n"
            + (cookie != null ? "Cookie: " + cookie + "\r\n" : "") + "\r\n";
        out.write(req.getBytes(StandardCharsets.UTF_8));
        out.flush();
        String status = line(in);
        if (!status.contains(" 101 ")) {
            socket.close();
            throw new IOException("no WebSocket: " + status);
        }
        while (!line(in).isEmpty()) { /* the rest of the headers */ }
    }

    private static String line(InputStream in) throws IOException {
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        for (int c; (c = in.read()) != '\n'; ) {
            if (c < 0) throw new IOException("closed");
            if (c != '\r') b.write(c);
        }
        return b.toString("UTF-8");
    }

    synchronized void sendText(String s) throws IOException { frame(1, s.getBytes(StandardCharsets.UTF_8)); }

    synchronized void sendBinary(byte[] b, int len) throws IOException {
        byte[] p = new byte[len];
        System.arraycopy(b, 0, p, 0, len);
        frame(2, p);
    }

    private void frame(int op, byte[] p) throws IOException {
        if (closed) throw new IOException("closed");
        ByteArrayOutputStream f = new ByteArrayOutputStream(p.length + 14);
        f.write(0x80 | op);
        if (p.length < 126) f.write(0x80 | p.length);
        else if (p.length < 65536) { f.write(0x80 | 126); f.write(p.length >> 8); f.write(p.length); }
        else { f.write(0x80 | 127); for (int i = 7; i >= 0; i--) f.write((int) ((long) p.length >> (8 * i))); }
        byte[] mask = new byte[4];
        RNG.nextBytes(mask);
        f.write(mask);
        for (int i = 0; i < p.length; i++) f.write(p[i] ^ mask[i & 3]);
        out.write(f.toByteArray());
        out.flush();
    }

    /** Reads until the socket closes, giving each whole message to the listener. */
    void read(Listener l) throws IOException {
        ByteArrayOutputStream msg = new ByteArrayOutputStream();
        int kind = 0;
        while (!closed) {
            int b0 = in.readUnsignedByte(), b1 = in.readUnsignedByte();
            long len = b1 & 0x7f;
            if (len == 126) len = in.readUnsignedShort();
            else if (len == 127) len = in.readLong();
            byte[] mask = (b1 & 0x80) != 0 ? new byte[4] : null;
            if (mask != null) in.readFully(mask);
            byte[] p = new byte[(int) len];
            in.readFully(p);
            if (mask != null) for (int i = 0; i < p.length; i++) p[i] ^= mask[i & 3];
            int op = b0 & 0x0f;
            if (op == 8) { close(); return; }
            if (op == 9) { synchronized (this) { frame(10, p); } continue; }
            if (op == 10) continue;
            if (op != 0) { kind = op; msg.reset(); }
            msg.write(p);
            if ((b0 & 0x80) != 0) {
                if (kind == 1) l.text(msg.toString("UTF-8"));
                else if (kind == 2) l.binary(msg.toByteArray());
                msg.reset();
            }
        }
    }

    void close() {
        if (closed) return;
        try {
            synchronized (this) { frame(8, new byte[] {0x03, (byte) 0xe8}); }   // 1000: normal closure
        } catch (IOException e) {
            // already gone
        }
        closed = true;
        try {
            socket.close();
        } catch (IOException e) {
            // already gone
        }
    }
}
