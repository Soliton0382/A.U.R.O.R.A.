# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🌌 Where the Sun, the Moon and any object are, seen from a site (ROADMAP N30): no library, a few formulas.

The Sun and the Moon from the Astronomical Almanac's low-precision series (the Sun ~1′, the Moon ~0.3°, M235 against
astropy); a catalogue's J2000 place moved to the date (precession); the hour angle from the sidereal time; the Moon's
altitude seen from the ground (its parallax). Good for a night's plan — which object is how high, when it is dark, how
lit and how far the Moon is — never for pointing a telescope. Arrays (numpy): a catalogue of thousands × a night in
10-minute steps is one computation.

The site is the rounded one of the inventory (ast_inventory: one decimal of a degree): never the exact place."""
from __future__ import annotations

import numpy as np

J2000 = 2451545.0
DARK = -18.0                      # the Sun below 18°: astronomical night
NAUTICAL = -12.0
R = np.radians
D = np.degrees


def jd(epoch_s):
    """Julian date of Unix seconds (UTC)."""
    return np.asarray(epoch_s, dtype=float) / 86400.0 + 2440587.5


def lst(j, lon_deg):
    """The local sidereal time in degrees (east longitude positive)."""
    return (280.46061837 + 360.98564736629 * (j - J2000) + lon_deg) % 360.0


def _equatorial(lam, beta, eps):
    lam, beta, eps = R(lam), R(beta), R(eps)
    ra = np.arctan2(np.sin(lam) * np.cos(eps) - np.tan(beta) * np.sin(eps), np.cos(lam))
    dec = np.arcsin(np.sin(beta) * np.cos(eps) + np.cos(beta) * np.sin(eps) * np.sin(lam))
    return D(ra) % 360.0, D(dec)


def sun(j):
    """(ra°, dec°, ecliptic longitude°) of the Sun."""
    n = j - J2000
    g = R(357.528 + 0.9856003 * n)
    lam = (280.460 + 0.9856474 * n + 1.915 * np.sin(g) + 0.020 * np.sin(2 * g)) % 360.0
    ra, dec = _equatorial(lam, 0.0 * n, 23.439 - 0.0000004 * n)
    return ra, dec, lam


def moon(j):
    """(ra°, dec°, ecliptic longitude°, ecliptic latitude°, horizontal parallax°) of the Moon."""
    t = (j - J2000) / 36525.0
    s = lambda a, b: np.sin(R(a + b * t))                                            # noqa: E731
    c = lambda a, b: np.cos(R(a + b * t))                                            # noqa: E731
    lam = (218.32 + 481267.881 * t + 6.29 * s(135.0, 477198.87) - 1.27 * s(259.3, -413335.36)
           + 0.66 * s(235.7, 890534.22) + 0.21 * s(269.9, 954397.74) - 0.19 * s(357.5, 35999.05)
           - 0.11 * s(186.5, 966404.03)) % 360.0
    beta = (5.13 * s(93.3, 483202.02) + 0.28 * s(228.2, 960400.89) - 0.28 * s(318.3, 6003.15)
            - 0.17 * s(217.6, -407332.21))
    par = (0.9508 + 0.0518 * c(135.0, 477198.87) + 0.0095 * c(259.3, -413335.36) + 0.0078 * c(235.7, 890534.22)
           + 0.0028 * c(269.9, 954397.74))
    ra, dec = _equatorial(lam, beta, 23.439 - 0.0130 * t)
    return ra, dec, lam, beta, par


def precess(ra, dec, j):
    """A J2000 place moved to the date (the first-order rates: < 1″ a year off; ~0.4° in 2026)."""
    years = (np.asarray(j, dtype=float) - J2000) / 365.25
    m, n = 3.07496 * 15 / 3600, 20.0431 / 3600                     # degrees a year
    a, d = R(np.asarray(ra, dtype=float)), R(np.asarray(dec, dtype=float))
    ra2 = np.asarray(ra) + (m + n * np.sin(a) * np.tan(np.clip(d, -1.55, 1.55))) * years
    return ra2 % 360.0, np.asarray(dec) + n * np.cos(a) * years


def altitude(ra, dec, lat, lon, j):
    """Altitude° for every place × every time: ra/dec of shape (N,) or (N, T), j of shape (T,) → (N, T)."""
    ra, dec = np.atleast_1d(ra).astype(float), np.atleast_1d(dec).astype(float)
    if ra.ndim == 1:
        ra, dec = ra[:, None], dec[:, None]
    h = R(lst(np.atleast_1d(j), lon)[None, :] - ra)
    phi, d = R(lat), R(dec)
    return D(np.arcsin(np.clip(np.sin(phi) * np.sin(d) + np.cos(phi) * np.cos(d) * np.cos(h), -1, 1)))


def separation(ra1, dec1, ra2, dec2):
    """The angle between two places, in degrees (arrays broadcast)."""
    a1, d1, a2, d2 = R(ra1), R(dec1), R(ra2), R(dec2)
    return D(np.arccos(np.clip(np.sin(d1) * np.sin(d2) + np.cos(d1) * np.cos(d2) * np.cos(a1 - a2), -1, 1)))


def moon_lit(j):
    """The Moon's lit fraction, 0 (new) to 1 (full), from its elongation from the Sun."""
    _, _, ls = sun(j)
    _, _, lm, bm, _ = moon(j)
    cos_psi = np.cos(R(bm)) * np.cos(R(lm - ls))
    return (1 - cos_psi) / 2


def night(lat: float, lon: float, start_s: float, step_min: int = 10) -> dict:
    """From `start_s` (the local noon) to the next noon, every step: the Sun's and the Moon's altitude, the Moon's
    place and lit fraction, and the night's edges (astronomical dusk and dawn, None when it never gets dark)."""
    t = start_s + np.arange(0, 24 * 60 + step_min, step_min) * 60.0
    j = jd(t)
    sra, sdec, _ = sun(j)
    sun_alt = altitude(sra, sdec, lat, lon, j).diagonal()
    mra, mdec, _, _, par = moon(j)
    geo = altitude(mra, mdec, lat, lon, j).diagonal()
    moon_alt = geo - D(np.arcsin(np.sin(R(par)) * np.cos(R(geo))))      # seen from the ground: lower by the parallax
    dark = sun_alt < DARK
    idx = np.flatnonzero(dark)
    return {"t": t, "jd": j, "sun_alt": sun_alt, "moon_alt": moon_alt, "moon_ra": mra, "moon_dec": mdec,
            "moon_lit": moon_lit(j), "dark": dark,
            "dusk": float(t[idx[0]]) if idx.size else None, "dawn": float(t[idx[-1]]) if idx.size else None,
            "step_h": step_min / 60.0}
