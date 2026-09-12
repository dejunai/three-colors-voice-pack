#!/usr/bin/env python3
"""Peanuts-style muted-trombone speech synthesizer.

Builds wordless adult-voice lines as sequences of syllable nuclei
(short muted-trombone bursts) with gaps, breaths, and speech-like
F0 / timing — not tunes, stingers, or wah-wah melodies.

Usage:
    python3 synth_trombone_speech.py --audition
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import wave

import numpy as np

SR = 44100
FADE_MS = 10.0
PEAK_DBFS = -4.5
HEAD_SILENCE = 0.028
TAIL_SILENCE = 0.055
AUDITION_DIR_DEFAULT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "audition"
)

STYLES = (
    "neutral",
    "bureaucratic",
    "dismissive",
    "cautious",
    "questioning",
    "weary",
)

# Per-style duration targets (seconds). All stay inside 1.5–2.5.
STYLE_TARGET_SEC = {
    "neutral": 1.95,
    "bureaucratic": 2.12,
    "dismissive": 1.78,
    "cautious": 2.28,
    "questioning": 1.98,
    "weary": 2.32,
}

# Deterministic seeds so v1/v2 stay distinct and reproducible.
SEEDS = {
    ("neutral", 1): 1013,
    ("neutral", 2): 1729,
    ("bureaucratic", 1): 2048,
    ("bureaucratic", 2): 2659,
    ("dismissive", 1): 3110,
    ("dismissive", 2): 3779,
    ("cautious", 1): 4242,
    ("cautious", 2): 4816,
    ("questioning", 1): 5557,
    ("questioning", 2): 6121,
    ("weary", 1): 7001,
    ("weary", 2): 7683,
}


# ---------------------------------------------------------------------------
# DSP helpers
# ---------------------------------------------------------------------------

def _smoothstep(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def _one_pole_lp(x: np.ndarray, cutoff: float, sr: int = SR) -> np.ndarray:
    """Vector-friendly one-pole lowpass via recursive filter (small clips)."""
    if len(x) == 0:
        return x
    a = math.exp(-2.0 * math.pi * cutoff / sr)
    y = np.empty_like(x)
    y[0] = x[0] * (1.0 - a)
    acc = y[0]
    xm = x
    one_m_a = 1.0 - a
    for i in range(1, len(x)):
        acc = one_m_a * xm[i] + a * acc
        y[i] = acc
    return y


def _moving_avg(x: np.ndarray, win: int) -> np.ndarray:
    win = max(3, int(win) | 1)
    k = np.hanning(win)
    k /= k.sum()
    return np.convolve(x, k, mode="same")


def fade_edges(x: np.ndarray, fade_ms: float = FADE_MS, sr: int = SR) -> np.ndarray:
    n = len(x)
    fade = max(2, int(sr * fade_ms / 1000.0))
    fade = min(fade, max(2, n // 3))
    y = x.astype(np.float64, copy=True)
    ramp_in = np.linspace(0.0, 1.0, fade)
    ramp_out = np.linspace(1.0, 0.0, fade)
    y[:fade] *= ramp_in
    y[-fade:] *= ramp_out
    return y


def adsr_env(
    n: int,
    attack_s: float,
    decay_s: float,
    sustain: float,
    release_s: float,
    sr: int = SR,
) -> np.ndarray:
    """ADSR whose stages are clamped to fit n samples (short-syllable safe)."""
    if n <= 4:
        return np.hanning(max(n, 1))

    a = max(1, int(round(attack_s * sr)))
    d = max(1, int(round(decay_s * sr)))
    r = max(1, int(round(release_s * sr)))

    if a + d + r > n:
        scale = n / float(a + d + r + 1)
        a = max(1, int(a * scale))
        d = max(1, int(d * scale))
        r = max(1, int(r * scale))
        while a + d + r > n:
            if r > 1:
                r -= 1
            elif d > 1:
                d -= 1
            elif a > 1:
                a -= 1
            else:
                break
        if a + d + r > n:
            a, d, r = 1, 1, max(1, n - 2)

    s = n - a - d - r
    parts = [
        np.linspace(0.0, 1.0, a, endpoint=False),
        np.linspace(1.0, sustain, d, endpoint=False),
    ]
    if s > 0:
        # Tiny sag on the sustain (speech, not an organ hold).
        t = np.linspace(0.0, 1.0, s, endpoint=False)
        parts.append(sustain * (1.0 - 0.06 * t))
    parts.append(np.linspace(sustain * (1.0 - 0.06 * (s > 0)), 0.0, r))
    env = np.concatenate(parts)
    if len(env) < n:
        env = np.pad(env, (0, n - len(env)))
    return env[:n]


def fft_bandpass(x: np.ndarray, lo: float, hi: float, sr: int = SR) -> np.ndarray:
    n = len(x)
    if n < 8:
        return x
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    gain = np.zeros_like(freqs)
    # Raised-cosine edges (~120 Hz) so breaths don't click.
    edge = 120.0
    for i, f in enumerate(freqs):
        if lo <= f <= hi:
            gain[i] = 1.0
        elif lo - edge < f < lo:
            gain[i] = _smoothstep(np.array([(f - (lo - edge)) / edge]))[0]
        elif hi < f < hi + edge:
            gain[i] = _smoothstep(np.array([1.0 - (f - hi) / edge]))[0]
    return np.fft.irfft(spec * gain, n).astype(np.float64)


def breath_noise(n: int, rng: np.random.Generator, amp: float = 0.05) -> np.ndarray:
    if n < 8 or amp <= 0:
        return np.zeros(max(n, 0))
    x = rng.normal(0.0, 1.0, n)
    x = fft_bandpass(x, 420.0, 1750.0)
    env = np.hanning(n) ** 1.15
    # Soft inhale-ish tilt: a bit more energy in the first half.
    tilt = np.linspace(1.15, 0.75, n)
    y = x * env * tilt
    peak = np.max(np.abs(y)) + 1e-12
    return (amp / peak) * y * 0.35


def mute_contour(n: int, kind: str, amount: float) -> np.ndarray:
    """Articulation-like mute motion: transition early, then hold.

    Speech-like (CV formant move at onset), not a full-note wah cycle.
    Stressed kinds travel farther; unstressed stay near a mid mute.
    """
    t = np.linspace(0.0, 1.0, n)
    trans = _smoothstep(t / 0.38)
    amt = float(np.clip(amount, 0.12, 1.0))
    if kind == "wa":
        # Closed -> open (classic "wa").
        return 0.10 + amt * 0.78 * trans
    if kind == "ow":
        # Open -> closed (closing syllable / statement end).
        return 0.86 - amt * 0.62 * trans
    if kind == "uh":
        # Central, small move — unstressed nucleus.
        return 0.38 + amt * 0.18 * trans
    if kind == "eh":
        # Slightly brighter, modest open.
        return 0.28 + amt * 0.50 * trans
    if kind == "ye":
        dip = 0.14 * _smoothstep(np.clip(t / 0.16, 0.0, 1.0))
        return 0.30 - dip + amt * 0.52 * trans
    return 0.45 + 0.1 * trans


# ---------------------------------------------------------------------------
# Muted-trombone syllable
# ---------------------------------------------------------------------------

def trombone_syllable(
    dur: float,
    f0_hz: float,
    f0_end_hz: float,
    stress: float,
    wah: str,
    rng: np.random.Generator,
    style: str,
    is_final: bool,
    sr: int = SR,
) -> np.ndarray:
    n = max(8, int(round(dur * sr)))
    t = np.arange(n) / float(sr)
    stress = float(np.clip(stress, 0.15, 1.0))

    # Intra-syllable F0: mostly linear, tiny irregular wander (not vibrato).
    f0 = np.linspace(f0_hz, f0_end_hz, n)
    jitter = rng.normal(0.0, 0.0075, n)
    jitter = _moving_avg(jitter, int(0.012 * sr))
    f0 = f0 * (1.0 + jitter)
    f0 = np.clip(f0, 90.0, 520.0)

    phase = np.cumsum(2.0 * np.pi * f0 / sr)
    mute = mute_contour(n, wah, 0.34 + 0.66 * stress)

    # Closed mute is darker; open is a bit brighter. Wide F1 travel = audible "wa".
    f1 = 360.0 + mute * 1180.0
    f2 = 1180.0 + mute * 900.0
    q1 = 5.2
    q2 = 2.4

    sig = np.zeros(n, dtype=np.float64)
    nyq = sr * 0.5 - 200.0
    n_harm = 22 if stress > 0.55 else 17

    for h in range(1, n_harm + 1):
        fh = h * f0
        if fh.min() > nyq:
            break
        # Mute kills the raw fundamental; the moving mid formant is the peak
        # (Harmon / plunger character — otherwise it just buzzes like a square).
        if h == 1:
            base = 0.28 + 0.10 * mute
        elif h == 2:
            base = 0.16 + 0.10 * mute
        elif h % 2 == 1:
            base = 0.92 / (h ** 0.58)
        else:
            base = (0.16 + 0.14 * mute) / (h ** 1.02)

        g1 = 1.0 / (1.0 + ((fh - f1) / (f1 / q1)) ** 2)
        g2 = 0.48 / (1.0 + ((fh - f2) / (f2 / q2)) ** 2)
        hicut_hz = 2000.0 + mute * 1100.0
        hicut = np.exp(-((fh / hicut_hz) ** 2.0))
        closed = (0.50 + 0.50 * mute) ** (0.20 * h)
        amp = base * (0.05 + 3.4 * g1 + 1.05 * g2) * hicut * closed
        phi = rng.uniform(0.0, 0.25)
        ny_win = np.clip((nyq + 200.0 - fh) / 280.0, 0.0, 1.0)
        sig += amp * ny_win * np.sin(h * phase + phi)

    # Irregular rasp / growl (noise AM — not a musical tremolo).
    rasp = rng.normal(0.0, 1.0, n)
    rasp = _moving_avg(rasp, int(0.010 * sr))
    depth = 0.035 + 0.055 * stress
    if style == "weary":
        depth *= 0.7
    elif style == "dismissive":
        depth *= 1.15
    elif style == "bureaucratic":
        depth *= 0.75
    sig *= 1.0 + depth * rasp

    # Gated lip noise at the formant (very low).
    noise = rng.normal(0.0, 1.0, n)
    noise = fft_bandpass(noise, 500.0, 2200.0)
    gate = np.clip(np.abs(sig) / (np.percentile(np.abs(sig), 90) + 1e-9), 0.0, 1.0)
    gate = gate ** 1.2
    sig += (0.036 + 0.045 * stress) * noise * gate

    # Soft plosive-ish onset (lip / mute bump) — speech onset, not a click.
    onset_n = max(4, int(0.007 * sr))
    if onset_n < n:
        bump = np.zeros(n)
        bump[:onset_n] = np.hanning(onset_n * 2)[:onset_n]
        puff = fft_bandpass(rng.normal(0.0, 1.0, n), 300.0, 1400.0)
        sig += 0.07 * stress * bump * puff

    # Style-specific envelope.
    atk, dec, sus, rel = _style_adsr(style, stress, is_final, dur)
    env = adsr_env(n, atk, dec, sus, rel, sr)
    # Stressed syllables a bit louder; keep unstressed present.
    level = 0.42 + 0.58 * stress
    if style == "weary" and is_final:
        level *= 0.82
    if style == "questioning" and is_final:
        level *= 1.05
    if style == "dismissive" and is_final:
        level *= 0.92
    sig *= env * level
    return sig


def _style_adsr(style: str, stress: float, is_final: bool, dur: float):
    """Return (attack, decay, sustain, release) seconds."""
    atk = 0.007 + 0.004 * (1.0 - stress)
    dec = 0.022
    sus = 0.72 + 0.10 * stress
    rel = min(0.040, 0.22 * dur)

    if style == "neutral":
        if is_final:
            rel = min(0.085, 0.34 * dur)
            sus = 0.68
    elif style == "bureaucratic":
        atk = 0.008
        dec = 0.018
        sus = 0.70
        rel = min(0.032, 0.18 * dur)  # tidy, clipped endings
        if is_final:
            rel = min(0.038, 0.20 * dur)
    elif style == "dismissive":
        atk = 0.005
        dec = 0.014
        sus = 0.62
        rel = min(0.018, 0.12 * dur)  # abrupt
        if is_final:
            rel = min(0.016, 0.10 * dur)
    elif style == "cautious":
        atk = 0.012
        dec = 0.030
        sus = 0.66
        rel = min(0.055, 0.26 * dur)
        if is_final:
            rel = min(0.090, 0.32 * dur)
    elif style == "questioning":
        atk = 0.007
        sus = 0.78
        rel = min(0.036, 0.18 * dur)
        if is_final:
            # Hold energy through the rise; don't sigh off.
            sus = 0.84
            rel = min(0.048, 0.20 * dur)
    elif style == "weary":
        atk = 0.014
        dec = 0.040
        sus = 0.58
        rel = min(0.070, 0.30 * dur)
        if is_final:
            sus = 0.48
            rel = min(0.20, 0.48 * dur)  # trailing fade
    return atk, dec, sus, rel


# ---------------------------------------------------------------------------
# Phrase specs — speech, not tunes.
# Events: ("syl", dur, f0, f0_end, stress, wah)
#         ("gap", dur)
#         ("pause", dur)
#         ("breath", dur, amp)
# F0 in Hz, irregular (avoid scale degrees). ~5–9 syllables, often 1 mid pause.
# ---------------------------------------------------------------------------

def phrase_events(style: str, take: int):
    """Return a list of events. v1/v2 differ in count, grouping, inflection."""
    key = (style, take)

    # ---- NEUTRAL: plain conversational statement; even-ish, gentle fall ----
    if key == ("neutral", 1):
        # 7 syllables, pause after 3. "That's not how we handle it."
        return [
            ("syl", 0.195, 233, 239, 0.86, "wa"),
            ("gap", 0.040),
            ("syl", 0.108, 241, 236, 0.38, "uh"),
            ("gap", 0.034),
            ("syl", 0.215, 247, 242, 0.90, "wa"),
            ("pause", 0.145),
            ("breath", 0.088, 0.042),
            ("syl", 0.125, 234, 230, 0.44, "uh"),
            ("gap", 0.038),
            ("syl", 0.112, 226, 222, 0.40, "uh"),
            ("gap", 0.036),
            ("syl", 0.168, 218, 212, 0.72, "ow"),
            ("gap", 0.038),
            ("syl", 0.255, 208, 194, 0.80, "ow"),
        ]
    if key == ("neutral", 2):
        # 6 syllables, pause after 4. Different grouping / stress.
        return [
            ("syl", 0.118, 226, 230, 0.40, "uh"),
            ("gap", 0.036),
            ("syl", 0.210, 238, 243, 0.88, "wa"),
            ("gap", 0.034),
            ("syl", 0.110, 236, 232, 0.36, "uh"),
            ("gap", 0.038),
            ("syl", 0.200, 244, 238, 0.84, "eh"),
            ("pause", 0.165),
            ("syl", 0.128, 228, 220, 0.48, "uh"),
            ("gap", 0.042),
            ("syl", 0.270, 214, 198, 0.82, "ow"),
        ]

    # ---- BUREAUCRATIC: practiced official; measured, flat, tidy ----
    if key == ("bureaucratic", 1):
        # 8 syllables, 4+4, almost even timing, narrow F0.
        return [
            ("syl", 0.142, 221, 223, 0.55, "uh"),
            ("gap", 0.046),
            ("syl", 0.138, 223, 224, 0.50, "uh"),
            ("gap", 0.044),
            ("syl", 0.155, 226, 225, 0.72, "eh"),
            ("gap", 0.046),
            ("syl", 0.148, 224, 222, 0.58, "uh"),
            ("pause", 0.155),
            ("syl", 0.140, 222, 223, 0.52, "uh"),
            ("gap", 0.046),
            ("syl", 0.138, 221, 220, 0.50, "uh"),
            ("gap", 0.044),
            ("syl", 0.158, 223, 221, 0.70, "eh"),
            ("gap", 0.042),
            ("syl", 0.150, 220, 217, 0.60, "uh"),
        ]
    if key == ("bureaucratic", 2):
        # 7 syllables, 3+4 grouping, still flat, slightly different pace.
        return [
            ("syl", 0.132, 218, 219, 0.48, "uh"),
            ("gap", 0.048),
            ("syl", 0.130, 219, 220, 0.46, "uh"),
            ("gap", 0.046),
            ("syl", 0.168, 222, 221, 0.74, "wa"),
            ("pause", 0.170),
            ("syl", 0.136, 220, 220, 0.50, "uh"),
            ("gap", 0.048),
            ("syl", 0.134, 219, 218, 0.48, "uh"),
            ("gap", 0.046),
            ("syl", 0.136, 218, 217, 0.50, "uh"),
            ("gap", 0.044),
            ("syl", 0.162, 216, 214, 0.64, "eh"),
        ]

    # ---- DISMISSIVE: brushing aside; short syls, falling, abrupt ----
    if key == ("dismissive", 1):
        # 8 short syllables, hitch after 2, steep fall, abrupt last.
        return [
            ("syl", 0.138, 264, 256, 0.88, "wa"),
            ("gap", 0.026),
            ("syl", 0.095, 250, 244, 0.42, "uh"),
            ("pause", 0.105),
            ("syl", 0.142, 238, 230, 0.82, "ow"),
            ("gap", 0.024),
            ("syl", 0.096, 224, 218, 0.40, "uh"),
            ("gap", 0.022),
            ("syl", 0.124, 210, 202, 0.72, "ow"),
            ("gap", 0.024),
            ("syl", 0.092, 196, 190, 0.38, "uh"),
            ("gap", 0.020),
            ("syl", 0.118, 186, 178, 0.60, "ow"),
            ("gap", 0.018),
            ("syl", 0.162, 174, 160, 0.80, "ow"),
        ]
    if key == ("dismissive", 2):
        # 7 syllables, 2 + 5 burst. Different rhythm, still falling/clipped.
        return [
            ("syl", 0.152, 258, 248, 0.90, "wa"),
            ("gap", 0.022),
            ("syl", 0.108, 242, 234, 0.50, "ow"),
            ("pause", 0.118),
            ("syl", 0.118, 230, 222, 0.64, "eh"),
            ("gap", 0.020),
            ("syl", 0.098, 216, 208, 0.40, "uh"),
            ("gap", 0.020),
            ("syl", 0.112, 200, 192, 0.58, "ow"),
            ("gap", 0.018),
            ("syl", 0.100, 186, 178, 0.44, "uh"),
            ("gap", 0.016),
            ("syl", 0.178, 170, 156, 0.84, "ow"),
        ]

    # ---- CAUTIOUS: measured disclosure; slower, more pauses, small F0 ----
    if key == ("cautious", 1):
        # 6 syllables, pauses after 1 and after 3. Tiny pitch moves.
        return [
            ("syl", 0.175, 214, 216, 0.55, "uh"),
            ("pause", 0.185),
            ("breath", 0.095, 0.038),
            ("syl", 0.155, 217, 215, 0.48, "uh"),
            ("gap", 0.055),
            ("syl", 0.195, 219, 217, 0.70, "eh"),
            ("pause", 0.200),
            ("syl", 0.160, 216, 214, 0.50, "uh"),
            ("gap", 0.052),
            ("syl", 0.150, 213, 211, 0.46, "uh"),
            ("gap", 0.048),
            ("syl", 0.220, 210, 206, 0.68, "ow"),
        ]
    if key == ("cautious", 2):
        # 7 syllables, one longer mid pause (4 + 3). Hesitant start.
        return [
            ("syl", 0.188, 210, 212, 0.42, "uh"),
            ("gap", 0.070),
            ("syl", 0.130, 213, 211, 0.36, "uh"),
            ("gap", 0.048),
            ("syl", 0.170, 215, 214, 0.60, "eh"),
            ("gap", 0.050),
            ("syl", 0.145, 214, 212, 0.44, "uh"),
            ("pause", 0.230),
            ("breath", 0.100, 0.036),
            ("syl", 0.152, 212, 210, 0.48, "uh"),
            ("gap", 0.055),
            ("syl", 0.210, 209, 207, 0.66, "wa"),
            ("gap", 0.048),
            ("syl", 0.200, 206, 202, 0.58, "ow"),
        ]

    # ---- QUESTIONING: ordinary question; rising terminal (speech, not lick) ----
    if key == ("questioning", 1):
        # 6 syllables, tiny hitch after 3, rise across last two.
        return [
            ("syl", 0.138, 218, 222, 0.70, "wa"),
            ("gap", 0.038),
            ("syl", 0.112, 224, 220, 0.40, "uh"),
            ("gap", 0.036),
            ("syl", 0.155, 220, 224, 0.64, "eh"),
            ("pause", 0.100),
            ("syl", 0.122, 226, 232, 0.48, "uh"),
            ("gap", 0.040),
            ("syl", 0.172, 240, 254, 0.80, "wa"),
            ("gap", 0.038),
            ("syl", 0.255, 260, 288, 0.90, "eh"),
        ]
    if key == ("questioning", 2):
        # 7 syllables, pause then rising tag. Different count / grouping.
        return [
            ("syl", 0.140, 214, 218, 0.60, "wa"),
            ("gap", 0.038),
            ("syl", 0.112, 220, 217, 0.38, "uh"),
            ("gap", 0.036),
            ("syl", 0.155, 218, 222, 0.70, "eh"),
            ("pause", 0.150),
            ("breath", 0.070, 0.030),
            ("syl", 0.118, 226, 232, 0.50, "uh"),
            ("gap", 0.034),
            ("syl", 0.125, 236, 244, 0.55, "wa"),
            ("gap", 0.036),
            ("syl", 0.145, 250, 262, 0.72, "eh"),
            ("gap", 0.032),
            ("syl", 0.250, 268, 294, 0.90, "ye"),
        ]

    # ---- WEARY: tired cadence, droop, longer final fade ----
    if key == ("weary", 1):
        # 6 syllables, pause after 3, long trailing last.
        return [
            ("syl", 0.188, 208, 204, 0.62, "uh"),
            ("gap", 0.055),
            ("syl", 0.165, 202, 198, 0.48, "uh"),
            ("gap", 0.050),
            ("syl", 0.205, 196, 190, 0.70, "ow"),
            ("pause", 0.175),
            ("breath", 0.110, 0.048),
            ("syl", 0.172, 186, 180, 0.50, "uh"),
            ("gap", 0.052),
            ("syl", 0.190, 176, 170, 0.55, "ow"),
            ("gap", 0.048),
            ("syl", 0.335, 164, 148, 0.72, "ow"),
        ]
    if key == ("weary", 2):
        # 7 syllables, pause after 4, even more trailing.
        return [
            ("syl", 0.165, 202, 199, 0.50, "uh"),
            ("gap", 0.048),
            ("syl", 0.145, 198, 195, 0.42, "uh"),
            ("gap", 0.046),
            ("syl", 0.155, 194, 190, 0.55, "eh"),
            ("gap", 0.050),
            ("syl", 0.180, 188, 184, 0.64, "ow"),
            ("pause", 0.190),
            ("breath", 0.100, 0.044),
            ("syl", 0.160, 180, 176, 0.46, "uh"),
            ("gap", 0.050),
            ("syl", 0.148, 172, 168, 0.42, "uh"),
            ("gap", 0.046),
            ("syl", 0.355, 160, 142, 0.70, "ow"),
        ]

    raise KeyError("no phrase for %s v%d" % (style, take))


# ---------------------------------------------------------------------------
# Render / fit / write
# ---------------------------------------------------------------------------

def _events_raw_dur(events) -> float:
    total = 0.0
    for ev in events:
        if ev[0] in ("syl", "gap", "pause", "breath"):
            total += ev[1]
    return total + HEAD_SILENCE + TAIL_SILENCE


def fit_events(events, target: float, lo: float = 1.42, hi: float = 2.65):
    """Scale syllable + gap time toward target; keep breaths/pauses in ratio."""
    raw = _events_raw_dur(events)
    if 1.55 <= raw <= 2.45 and abs(raw - target) < 0.12:
        return events
    # Don't scale head/tail silence.
    body = raw - HEAD_SILENCE - TAIL_SILENCE
    want_body = target - HEAD_SILENCE - TAIL_SILENCE
    scale = want_body / max(body, 1e-6)
    # Allow a wide scale so short styles (dismissive) still hit medium length.
    scale = float(np.clip(scale, 0.70, 1.90))
    out = []
    for ev in events:
        kind = ev[0]
        if kind == "syl":
            out.append((kind, ev[1] * scale, *ev[2:]))
        elif kind in ("gap", "pause"):
            out.append((kind, ev[1] * scale))
        elif kind == "breath":
            # Keep breath short; only scale a little.
            bscale = 0.65 + 0.35 * scale
            out.append((kind, ev[1] * bscale, ev[2]))
        else:
            out.append(ev)
    return out


def render_events(events, style: str, rng: np.random.Generator, sr: int = SR) -> np.ndarray:
    chunks = [np.zeros(int(HEAD_SILENCE * sr))]
    syl_idxs = [i for i, ev in enumerate(events) if ev[0] == "syl"]
    last_syl = syl_idxs[-1] if syl_idxs else -1

    for i, ev in enumerate(events):
        kind = ev[0]
        if kind == "syl":
            _, dur, f0, f0e, stress, wah = ev
            chunks.append(
                trombone_syllable(
                    dur=dur,
                    f0_hz=f0,
                    f0_end_hz=f0e,
                    stress=stress,
                    wah=wah,
                    rng=rng,
                    style=style,
                    is_final=(i == last_syl),
                    sr=sr,
                )
            )
        elif kind in ("gap", "pause"):
            chunks.append(np.zeros(max(1, int(ev[1] * sr))))
        elif kind == "breath":
            chunks.append(breath_noise(max(8, int(ev[1] * sr)), rng, amp=ev[2]))
    chunks.append(np.zeros(int(TAIL_SILENCE * sr)))
    return np.concatenate(chunks)


def normalize_peak(x: np.ndarray, peak_db: float = PEAK_DBFS) -> np.ndarray:
    x = fade_edges(x, FADE_MS)
    peak = float(np.max(np.abs(x))) + 1e-12
    target = 10.0 ** (peak_db / 20.0)
    y = x * (target / peak)
    # Hard safety — should never hit after normalize.
    return np.clip(y, -0.92, 0.92)


def write_wav(path: str, x: np.ndarray, sr: int = SR) -> None:
    pcm = np.int16(np.round(np.clip(x, -1.0, 1.0) * 32767.0))
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def analyze(x: np.ndarray, sr: int = SR):
    dur = len(x) / float(sr)
    peak = float(np.max(np.abs(x))) + 1e-12
    peak_db = 20.0 * math.log10(peak)
    rms = float(np.sqrt(np.mean(x.astype(np.float64) ** 2))) + 1e-12
    rms_db = 20.0 * math.log10(rms)
    return dur, peak_db, rms_db


def render_clip(style: str, take: int, sr: int = SR) -> np.ndarray:
    rng = np.random.default_rng(SEEDS[(style, take)])
    events = fit_events(phrase_events(style, take), STYLE_TARGET_SEC[style])
    x = render_events(events, style, rng, sr=sr)
    x = normalize_peak(x, PEAK_DBFS)
    return x


def ensure_duration(style: str, take: int, sr: int = SR, attempts: int = 6) -> np.ndarray:
    """Render and, if needed, nudge timing so duration sits in 1.4–2.7s."""
    target = STYLE_TARGET_SEC[style]
    lo, hi = 1.40, 2.70
    events = phrase_events(style, take)
    for k in range(attempts):
        rng = np.random.default_rng(SEEDS[(style, take)] + k * 17)
        fitted = fit_events(events, target)
        x = normalize_peak(render_events(fitted, style, rng, sr=sr))
        dur = len(x) / float(sr)
        if lo <= dur <= hi:
            return x
        # Nudge target and try again (syllable/gap scale).
        if dur < lo:
            target = min(2.45, target + 0.18)
        else:
            target = max(1.55, target - 0.18)
    return x


def write_readme(out_dir: str, rows) -> None:
    path = os.path.join(out_dir, "README.md")
    lines = [
        "# Trombone speech — first audition batch",
        "",
        "Muted-trombone *adult voice* clips in the Peanuts animated-special register:",
        "syllable pulses, pauses, breaths, emphasis, rising/falling inflection.",
        "**No intelligible words.** Not melodies, punchlines, or stingers.",
        "",
        "## Specs",
        "- Instrument: trombone (muted / plunger-like)",
        "- Length: medium (target 1.5–2.5 s)",
        "- Format: mono WAV, 44.1 kHz, 16-bit PCM",
        "- Peak: about −3 to −6 dBFS, no clipping",
        "- Dry: no reverb tail, no bed music, no other instruments",
        "- Clean edges: ~10 ms fade in/out",
        "",
        "## Criteria (listen for)",
        "- Sounds like talking, not a tune",
        "- Each clip is one sentence-ish line (5–9 syllables, often a mid pause)",
        "- Styles are distinct on playback:",
        "  - **neutral** — plain conversational statement; even-ish rhythm, gentle terminal fall",
        "  - **bureaucratic** — practiced official wording; measured pace, flatter contour, tidy ending",
        "  - **dismissive** — brushing aside; shorter syllables, falling contour, abrupt finish",
        "  - **cautious** — carefully measured disclosure; slower, more pauses, small pitch moves",
        "  - **questioning** — ordinary question; rising terminal inflection (speech rise, not an up-lick)",
        "  - **weary** — tired cadence; drooping pitch, longer final syllable fade",
        "- v1 vs v2: different syllable count / pause placement / inflection, not a pitch shift",
        "",
        "## Files",
        "",
        "| File | Style | Take | Duration | Peak dBFS |",
        "|------|-------|------|----------|-----------|",
    ]
    for name, style, take, dur, peak_db in rows:
        lines.append(
            "| `%s` | %s | v%d | %.2fs | %.1f |"
            % (name, style, take, dur, peak_db)
        )
    lines.extend(
        [
            "",
            "Regenerate this batch:",
            "",
            "```",
            "python3 /workspace/three-colors-voice-pack/synth_trombone_speech.py --audition",
            "```",
            "",
        ]
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def run_audition(out_dir: str) -> int:
    os.makedirs(out_dir, exist_ok=True)
    rows = []
    print("style            take  file                                  dur     peak")
    print("-" * 78)
    for style in STYLES:
        for take in (1, 2):
            name = "trombone_%s_medium_v%d.wav" % (style, take)
            path = os.path.join(out_dir, name)
            x = ensure_duration(style, take)
            write_wav(path, x)
            dur, peak_db, rms_db = analyze(x)
            print(
                "%-16s v%d   %-36s %5.2fs  %6.1f dBFS  (rms %5.1f)"
                % (style, take, name, dur, peak_db, rms_db)
            )
            rows.append((name, style, take, dur, peak_db))
            if not (1.40 <= dur <= 2.70):
                print("  WARNING: duration outside 1.4–2.7s", file=sys.stderr)
            if peak_db > -2.8 or peak_db < -7.0:
                print("  WARNING: peak dBFS out of band", file=sys.stderr)
    write_readme(out_dir, rows)
    print("-" * 78)
    print("wrote %d files + README.md -> %s" % (len(rows), out_dir))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Muted-trombone speech synthesizer")
    p.add_argument(
        "--audition",
        action="store_true",
        help="Generate the first 12-file medium trombone audition batch",
    )
    p.add_argument(
        "--out",
        default=AUDITION_DIR_DEFAULT,
        help="Audition output directory (default: alongside this script)",
    )
    args = p.parse_args(argv)
    if args.audition:
        return run_audition(os.path.abspath(args.out))
    p.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
