# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora Desktop's icon as text inside a signed file (an .svg is outside the owner's signature, and root's copy takes
only signed files): Aurora's A in its ring, the web app's colours, with a small screen. `aurora-root install desk`
writes it to /usr/local/share/icons/hicolor/scalable/apps/aurora-desk.svg; the app loads it from here."""

SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <!-- Aurora Desktop: Aurora's icon (the A in its ring, same colours as webui/assets/icon-512.png) with a small
       screen, so it is told apart from the web app at a glance. -->
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#1e143d"/>
      <stop offset="1" stop-color="#6d31b2"/>
    </linearGradient>
  </defs>
  <rect width="512" height="512" fill="url(#bg)"/>
  <circle cx="256" cy="256" r="190" fill="none" stroke="#818cf8" stroke-width="12"/>
  <path d="M256 128 L336 352 H296 L280 304 H232 L216 352 H176 Z M244 268 H268 L256 228 Z" fill="#e8e9ff"/>
  <g transform="translate(330 330)">
    <rect x="0" y="0" width="140" height="96" rx="12" fill="#1e143d" stroke="#818cf8" stroke-width="10"/>
    <rect x="16" y="16" width="108" height="64" rx="4" fill="#818cf8" opacity="0.35"/>
    <rect x="56" y="96" width="28" height="18" fill="#818cf8"/>
    <rect x="36" y="112" width="68" height="10" rx="5" fill="#818cf8"/>
  </g>
</svg>
"""
