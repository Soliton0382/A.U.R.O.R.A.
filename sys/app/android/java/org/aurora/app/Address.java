// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 A.U.R.O.R.A. Project
package org.aurora.app;

import java.net.URI;
import java.util.Locale;

/** Aurora's address as the owner typed it, and whether a link stays inside it. Plain Java: tested off the phone. */
final class Address {
    private Address() {}

    /** "https://host[:port]" with no path, or null when the text is not an HTTPS address with a name. */
    static String normalize(String typed) {
        if (typed == null) return null;
        String s = typed.trim();
        if (s.isEmpty()) return null;
        if (!s.contains("://")) s = "https://" + s;
        try {
            URI u = new URI(s);
            if (!"https".equals(String.valueOf(u.getScheme()).toLowerCase(Locale.ROOT))) return null;
            String host = u.getHost();
            if (host == null || host.isEmpty() || u.getUserInfo() != null) return null;
            int port = u.getPort();
            return "https://" + host.toLowerCase(Locale.ROOT) + (port > 0 && port != 443 ? ":" + port : "");
        } catch (Exception e) {
            return null;
        }
    }

    /** The welcome form's two fields: an IP or a name (or a whole address), and a port; empty port = 443. */
    static String of(String host, String port) {
        String n = normalize(host), p = port == null ? "" : port.trim();
        if (n == null || p.isEmpty()) return n;
        if (!p.matches("[0-9]{1,5}") || Integer.parseInt(p) < 1 || Integer.parseInt(p) > 65535) return null;
        try {
            String h = new URI(n).getHost();
            return "https://" + h + ("443".equals(p) ? "" : ":" + Integer.parseInt(p));
        } catch (Exception e) {
            return null;
        }
    }

    /** True when the url is Aurora's own page (same scheme, host and port): it opens here, anything else outside. */
    static boolean inside(String base, String url) {
        if (base == null || url == null) return false;
        try {
            URI b = new URI(base), u = new URI(url);
            int bp = b.getPort() > 0 ? b.getPort() : 443, up = u.getPort() > 0 ? u.getPort() : 443;
            return "https".equalsIgnoreCase(u.getScheme()) && b.getHost() != null
                && b.getHost().equalsIgnoreCase(u.getHost()) && bp == up;
        } catch (Exception e) {
            return false;
        }
    }
}
