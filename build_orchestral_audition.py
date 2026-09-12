#!/usr/bin/env python3
"""Build Peanuts-style orchestral voice audition from REAL instrument samples.

Source: University of Iowa Musical Instrument Samples (MIS) — real tenor trombone
and violin arco recordings, split into note grains, then concatenated into
speech-like syllable phrases with physical articulations.

Does NOT use additive sine / chiptune synthesis as the voice source.
"""

from __future__ import annotations

import math
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 44100
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "source_samples"
OUT = ROOT / "audition_orchestral"
TARGET_PEAK_DB = -4.5  # mid of -3..-6


# ---------------------------------------------------------------------------
# I/O + DSP helpers
# ---------------------------------------------------------------------------

def load(path: Path) -> np.ndarray:
    x, sr = sf.read(str(path))
    if sr != SR:
        # resample with ffmpeg if needed
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as t:
            tmp = t.name
        subprocess.check_call(
            ["ffmpeg", "-y", "-i", str(path), "-ac", "1", "-ar", str(SR), tmp],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        x, _ = sf.read(tmp)
        os.unlink(tmp)
    if x.ndim > 1:
        x = x.mean(axis=1)
    return x.astype(np.float64)


def write_wav(path: Path, x: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # peak normalize to TARGET_PEAK_DB
    peak = float(np.max(np.abs(x))) + 1e-12
    target = 10 ** (TARGET_PEAK_DB / 20.0)
    x = x * (target / peak)
    # hard clip safety
    x = np.clip(x, -0.99, 0.99)
    sf.write(str(path), x.astype(np.float32), SR, subtype="PCM_16")


def fade(x: np.ndarray, fade_in_ms: float = 3.0, fade_out_ms: float = 8.0) -> np.ndarray:
    x = x.copy()
    n_in = max(1, int(SR * fade_in_ms / 1000.0))
    n_out = max(1, int(SR * fade_out_ms / 1000.0))
    if len(x) > n_in + n_out:
        x[:n_in] *= np.linspace(0.0, 1.0, n_in)
        x[-n_out:] *= np.linspace(1.0, 0.0, n_out)
    return x


def one_pole_lp(x: np.ndarray, cutoff_hz: float) -> np.ndarray:
    """Simple one-pole lowpass (for mute body, not as voice source)."""
    if len(x) == 0:
        return x
    a = math.exp(-2.0 * math.pi * cutoff_hz / SR)
    y = np.empty_like(x)
    s = 0.0
    for i, v in enumerate(x):
        s = (1 - a) * v + a * s
        y[i] = s
    return y


def resonant_mute(x: np.ndarray, base_cut: float = 1400.0, wah: float = 0.35) -> np.ndarray:
    """Gentle wah / plunger-mute color OVER real brass — never replaces it.

    Mostly keeps open trombone; lightly darkens with a moving LP and
    blends a band-emphasized mid so the mute feels physical, not telephone.
    """
    n = len(x)
    if n == 0:
        return x
    t = np.linspace(0, 1, n)
    cut = base_cut * (1.0 + wah * (0.45 * np.sin(2 * math.pi * (0.55 + 0.5 * t) * t)
                                   + 0.22 * np.sin(2 * math.pi * 1.9 * t + 0.4)))
    y = np.zeros_like(x)
    block = 128
    s = 0.0
    for i in range(0, n, block):
        j = min(n, i + block)
        c = float(np.mean(cut[i:j]))
        a = math.exp(-2.0 * math.pi * max(600.0, c) / SR)
        for k in range(i, j):
            s = (1 - a) * x[k] + a * s
            y[k] = s
    # Keep majority open brass so timbre stays orchestral
    openish = one_pole_lp(x, 5200.0)
    mix = 0.38 * y + 0.62 * openish
    residual = x - one_pole_lp(x, 900.0)
    mix = mix + 0.22 * np.tanh(1.8 * residual)
    return mix


def breath_noise(dur: float, amp: float = 0.012) -> np.ndarray:
    n = int(dur * SR)
    if n <= 0:
        return np.zeros(0)
    rng = np.random.default_rng(int(dur * 1e6) % 2**31)
    noise = rng.normal(0, 1, n)
    # band-limit to breath-ish band
    noise = one_pole_lp(noise, 1800.0) - one_pole_lp(noise, 200.0)
    env = np.hanning(n) if n > 2 else np.ones(n)
    return amp * noise * env


def silence(dur: float) -> np.ndarray:
    return np.zeros(max(0, int(dur * SR)))


def extract_syllable_grain(
    note: np.ndarray,
    dur: float,
    attack_bias: float = 0.0,
    sustain_start_frac: float = 0.08,
) -> np.ndarray:
    """Cut a syllable-length grain preferring the real attack + early sustain."""
    need = max(32, int(dur * SR))
    n = len(note)
    # find energetic attack region
    win = int(0.01 * SR)
    e = np.array([np.sqrt(np.mean(note[i : i + win] ** 2)) for i in range(0, max(1, n - win), win)])
    if len(e) == 0:
        return fade(note[:need] if n >= need else np.pad(note, (0, need - n)))
    onset = int(np.argmax(e > 0.25 * np.max(e))) * win
    onset = max(0, onset - int(0.008 * SR))
    # start a bit into sustain for variety when attack_bias < 0
    start = onset + int(max(0.0, sustain_start_frac - attack_bias) * n * 0.15)
    start = min(start, max(0, n - need // 3))
    chunk = note[start : start + need]
    if len(chunk) < need:
        # loop sustain gently if note shorter than needed (rare for Iowa)
        if len(chunk) < 64:
            chunk = np.pad(chunk, (0, need - len(chunk)))
        else:
            sus = chunk[len(chunk) // 3 :]
            while len(chunk) < need:
                # crossfade loop
                take = min(len(sus), need - len(chunk))
                chunk = np.concatenate([chunk, sus[:take]])
            chunk = chunk[:need]
    return fade(chunk.astype(np.float64), 2.0, 6.0)


def pitch_shift_resample(x: np.ndarray, semitones: float) -> np.ndarray:
    """Pitch shift via resampling (also changes duration — speech-like lip/finger slide)."""
    if abs(semitones) < 0.01:
        return x
    ratio = 2 ** (semitones / 12.0)
    n_out = max(1, int(len(x) / ratio))
    t_old = np.linspace(0, 1, len(x), endpoint=False)
    t_new = np.linspace(0, 1, n_out, endpoint=False)
    return np.interp(t_new, t_old, x)


def pitch_slide(x: np.ndarray, start_st: float, end_st: float) -> np.ndarray:
    """Time-varying pitch via piecewise resampling windows (lip slur / portamento)."""
    if abs(start_st - end_st) < 0.05 and abs(start_st) < 0.05:
        return x
    # process in overlapping grains
    grain = int(0.028 * SR)
    hop = int(0.012 * SR)
    if len(x) < grain * 2:
        return pitch_shift_resample(x, 0.5 * (start_st + end_st))
    out = np.zeros(len(x) + hop)
    w = np.hanning(grain)
    pos = 0
    read = 0
    while read + grain < len(x) and pos + grain < len(out):
        frac = read / max(1, len(x) - grain)
        st = start_st + (end_st - start_st) * frac
        g = x[read : read + grain] * w
        g2 = pitch_shift_resample(g, st)
        # fit into hop-aligned slot
        if len(g2) < grain:
            g2 = np.pad(g2, (0, grain - len(g2)))
        else:
            g2 = g2[:grain]
            g2 *= w  # re-window after resample length change approx
        out[pos : pos + grain] += g2
        read += hop
        pos += hop
    # normalize overlap
    peak = np.max(np.abs(out)) + 1e-12
    src_peak = np.max(np.abs(x)) + 1e-12
    out = out * (src_peak / peak)
    return out[: len(x)]


def time_scale_rubberband(x: np.ndarray, factor: float) -> np.ndarray:
    """Time-stretch preserving pitch via rubberband-cli when available."""
    if abs(factor - 1.0) < 0.03:
        return x
    with tempfile.TemporaryDirectory() as td:
        inp = Path(td) / "in.wav"
        outp = Path(td) / "out.wav"
        sf.write(str(inp), x.astype(np.float32), SR)
        # rubberband -t tempo: >1 = longer
        cmd = ["rubberband", "-t", f"{factor:.4f}", "-q", str(inp), str(outp)]
        try:
            subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            y, _ = sf.read(str(outp))
            if y.ndim > 1:
                y = y.mean(1)
            return y.astype(np.float64)
        except Exception:
            # fallback: crude resample then pad/trim (pitch shifts — use sparingly)
            return pitch_shift_resample(x, -12 * math.log2(factor))


def apply_gain_env(x: np.ndarray, shape: str = "speech") -> np.ndarray:
    n = len(x)
    t = np.linspace(0, 1, n)
    if shape == "speech":
        # quick tongue attack, slight mid swell, soft release
        env = (1 - np.exp(-18 * t)) * (0.85 + 0.15 * np.sin(math.pi * t)) * (1 - 0.35 * t ** 1.4)
    elif shape == "fall":
        env = (1 - np.exp(-22 * t)) * (1.0 - 0.72 * t ** 0.9)
    elif shape == "swell_fade":
        env = (1 - np.exp(-10 * t)) * (1.0 - 0.85 * t ** 1.6)
    elif shape == "soft":
        env = (1 - np.exp(-8 * t)) * (0.9 - 0.25 * t)
    else:
        env = np.ones(n)
    return x * env


# ---------------------------------------------------------------------------
# Phrase definitions (speech syllables, not melodies)
# ---------------------------------------------------------------------------

# Trombone note pools (C3=0 ... B3=11 in notes_mf_c3)
TB_MF = SRC / "trombone" / "notes_mf_c3"
TB_FF = SRC / "trombone" / "notes_ff_c3"
TB_PP = SRC / "trombone" / "notes_pp_c3"
TB_MF4 = SRC / "trombone" / "notes_mf_c4"

VN_MF_G = SRC / "violin" / "notes_mf_g_b3"   # B3..B4
VN_MF_LOW = SRC / "violin" / "notes_mf_g_g3"  # G3.. ~
VN_PP = SRC / "violin" / "notes_pp_g_b3"
VN_FF = SRC / "violin" / "notes_ff_g_g3"
VN_D = SRC / "violin" / "notes_mf_d_d4"


def note_path(folder: Path, idx: int) -> Path:
    files = sorted(folder.glob("note_*.wav"))
    return files[idx % len(files)]


def make_tb_syll(
    note_idx: int,
    dur: float,
    dyn: str = "mf",
    slide: tuple[float, float] = (0.0, 0.0),
    mute_wah: float = 0.4,
    env: str = "speech",
    gain: float = 1.0,
) -> np.ndarray:
    folder = {"mf": TB_MF, "ff": TB_FF, "pp": TB_PP, "mf4": TB_MF4}[dyn]
    note = load(note_path(folder, note_idx))
    # Prefer attack for tonguing; take ~1.1x then scale
    grain = extract_syllable_grain(note, min(dur * 1.15, 0.55), attack_bias=0.15)
    # time to exact duration
    factor = (dur * SR) / max(1, len(grain))
    if 0.55 < factor < 1.8:
        grain = time_scale_rubberband(grain, factor)
    else:
        # cut or pad
        need = int(dur * SR)
        if len(grain) > need:
            grain = grain[:need]
        else:
            grain = np.pad(grain, (0, need - len(grain)))
    grain = pitch_slide(grain, slide[0], slide[1])
    grain = apply_gain_env(grain, env)
    grain = resonant_mute(grain, base_cut=1500.0, wah=mute_wah)
    # Layer a short real ff attack for audible tonguing / lip effort
    try:
        atk = load(note_path(TB_FF, note_idx))
        atk_g = extract_syllable_grain(atk, min(0.055, dur * 0.35), attack_bias=0.35)
        n = min(len(atk_g), len(grain), int(0.06 * SR))
        if n > 16:
            grain[:n] += 0.35 * atk_g[:n] * np.linspace(1.0, 0.15, n)
    except Exception:
        pass
    click_n = min(int(0.014 * SR), len(grain) // 4)
    if click_n > 4:
        grain[:click_n] *= np.linspace(1.45, 1.0, click_n)
    return fade(grain * gain, 1.2, 8.0)


def make_vn_syll(
    note_idx: int,
    dur: float,
    pool: str = "mf",
    slide: tuple[float, float] = (0.0, 0.0),
    env: str = "speech",
    gain: float = 1.0,
    bow_noise: float = 0.02,
) -> np.ndarray:
    folder = {"mf": VN_MF_G, "low": VN_MF_LOW, "pp": VN_PP, "ff": VN_FF, "d": VN_D}[pool]
    note = load(note_path(folder, note_idx))
    grain = extract_syllable_grain(note, min(dur * 1.2, 0.7), attack_bias=0.2, sustain_start_frac=0.05)
    factor = (dur * SR) / max(1, len(grain))
    if 0.5 < factor < 2.0:
        grain = time_scale_rubberband(grain, factor)
    else:
        need = int(dur * SR)
        grain = grain[:need] if len(grain) > need else np.pad(grain, (0, need - len(grain)))
    grain = pitch_slide(grain, slide[0], slide[1])
    grain = apply_gain_env(grain, env)
    # subtle bow scrape texture from filtered noise at attack
    if bow_noise > 0:
        bn = breath_noise(min(0.045, dur * 0.25), amp=bow_noise)
        # brighten a bit for bow hair
        if len(bn):
            bn = bn - one_pole_lp(bn, 600.0)
            grain[: len(bn)] += bn
    # Keep most of the raw arco; tiny body blend only
    body = one_pole_lp(grain, 4500.0)
    grain = 0.9 * grain + 0.1 * body
    # bow-direction change: mid-syllable micro dip + re-attack if long
    if len(grain) > int(0.22 * SR):
        mid = len(grain) // 2
        w = int(0.012 * SR)
        grain[mid : mid + w] *= np.linspace(1.0, 0.55, w)
        grain[mid + w : mid + 2 * w] *= np.linspace(0.55, 1.08, w)
    return fade(grain * gain, 1.5, 12.0)


def concat_phrase(parts: list[np.ndarray], head: float = 0.03, tail: float = 0.06) -> np.ndarray:
    chunks = [silence(head)]
    for p in parts:
        chunks.append(p)
    chunks.append(silence(tail))
    y = np.concatenate(chunks)
    # DC block
    y = y - np.mean(y)
    return y


# ---------------------------------------------------------------------------
# Four audition phrases
# ---------------------------------------------------------------------------

def phrase_trombone_bureaucratic() -> np.ndarray:
    """Practiced official wording; steady measured pace; flatter contour; tidy ending.
    Syllables approx: 'as-per-our-re-cords-sir' (6)
    """
    parts = []
    # as-
    parts.append(make_tb_syll(5, 0.22, "mf", slide=(0.0, 0.1), mute_wah=0.32, env="speech", gain=0.95))
    parts.append(silence(0.055))
    # per-
    parts.append(make_tb_syll(5, 0.18, "mf", slide=(0.0, -0.15), mute_wah=0.28, env="speech", gain=0.9))
    parts.append(silence(0.045))
    # our-
    parts.append(make_tb_syll(7, 0.26, "mf", slide=(-0.1, 0.2), mute_wah=0.35, env="speech", gain=1.0))
    parts.append(silence(0.07))
    # re-
    parts.append(make_tb_syll(7, 0.16, "mf", slide=(0.0, 0.0), mute_wah=0.3, env="speech", gain=0.88))
    parts.append(silence(0.04))
    # cords-
    parts.append(make_tb_syll(8, 0.34, "mf", slide=(0.15, -0.25), mute_wah=0.38, env="speech", gain=1.05))
    parts.append(silence(0.08))
    # brief breath
    parts.append(breath_noise(0.07, 0.018))
    parts.append(silence(0.03))
    # sir. (tidy fall, quieter)
    parts.append(make_tb_syll(5, 0.30, "pp", slide=(0.1, -0.6), mute_wah=0.25, env="fall", gain=1.4))
    return concat_phrase(parts, 0.035, 0.07)


def phrase_trombone_dismissive() -> np.ndarray:
    """Brushing aside; shorter syllables; falling contour; abrupt finish.
    Syllables: 'oh-come-on-not-that-now' (6) clipped final — denser articulations
    totaling ~2.0s without empty pad.
    """
    parts = []
    parts.append(make_tb_syll(9, 0.20, "ff", slide=(0.55, -0.4), mute_wah=0.52, env="fall", gain=0.82))
    parts.append(silence(0.05))
    parts.append(make_tb_syll(8, 0.24, "mf", slide=(0.2, -0.6), mute_wah=0.48, env="fall", gain=0.95))
    parts.append(silence(0.045))
    parts.append(make_tb_syll(6, 0.26, "mf", slide=(0.05, -0.75), mute_wah=0.5, env="fall", gain=1.0))
    parts.append(silence(0.08))
    parts.append(breath_noise(0.06, 0.022))
    parts.append(silence(0.05))
    parts.append(make_tb_syll(5, 0.16, "mf", slide=(-0.2, -0.5), mute_wah=0.45, env="speech", gain=0.92))
    parts.append(silence(0.04))
    parts.append(make_tb_syll(4, 0.18, "mf", slide=(0.0, -0.75), mute_wah=0.52, env="fall", gain=0.9))
    parts.append(silence(0.045))
    parts.append(make_tb_syll(2, 0.26, "ff", slide=(0.15, -1.55), mute_wah=0.58, env="fall", gain=0.78))
    parts.append(silence(0.02))
    parts.append(breath_noise(0.035, 0.03))
    return concat_phrase(parts, 0.03, 0.06)


def phrase_violin_cautious() -> np.ndarray:
    """Carefully measured disclosure; slower; more pauses; smaller pitch moves.
    Syllables: 'well-I-suppose-we-might' (5) with hesitations
    """
    parts = []
    parts.append(make_vn_syll(2, 0.28, "mf", slide=(0.0, 0.15), env="soft", gain=1.0, bow_noise=0.025))
    parts.append(silence(0.11))
    parts.append(breath_noise(0.04, 0.008))  # bow lift whisper
    parts.append(silence(0.05))
    parts.append(make_vn_syll(3, 0.18, "mf", slide=(0.1, 0.0), env="speech", gain=0.85, bow_noise=0.02))
    parts.append(silence(0.09))
    parts.append(make_vn_syll(4, 0.36, "mf", slide=(-0.15, 0.25), env="soft", gain=0.95, bow_noise=0.018))
    parts.append(silence(0.12))
    parts.append(make_vn_syll(3, 0.20, "pp", slide=(0.0, -0.1), env="soft", gain=1.3, bow_noise=0.015))
    parts.append(silence(0.10))
    parts.append(make_vn_syll(5, 0.42, "mf", slide=(0.05, -0.35), env="swell_fade", gain=0.9, bow_noise=0.022))
    return concat_phrase(parts, 0.04, 0.08)


def phrase_violin_weary() -> np.ndarray:
    """Tired cadence; trailing endings; drooping pitch; longer final fade.
    Syllables: 'I-am-so-tired-of-this' (6) trailing
    """
    parts = []
    parts.append(make_vn_syll(1, 0.22, "low", slide=(0.0, -0.2), env="soft", gain=0.9, bow_noise=0.02))
    parts.append(silence(0.07))
    parts.append(make_vn_syll(1, 0.18, "mf", slide=(-0.1, -0.15), env="speech", gain=0.8, bow_noise=0.015))
    parts.append(silence(0.06))
    parts.append(make_vn_syll(0, 0.26, "mf", slide=(0.0, -0.4), env="fall", gain=0.85, bow_noise=0.018))
    parts.append(silence(0.08))
    parts.append(make_vn_syll(2, 0.34, "mf", slide=(-0.2, -0.6), env="fall", gain=0.95, bow_noise=0.02))
    parts.append(silence(0.09))
    parts.append(make_vn_syll(1, 0.20, "pp", slide=(-0.1, -0.3), env="soft", gain=1.2, bow_noise=0.012))
    parts.append(silence(0.07))
    # long trailing final syllable with droop
    final = make_vn_syll(0, 0.55, "low", slide=(-0.3, -1.4), env="swell_fade", gain=0.85, bow_noise=0.015)
    # extra long fade
    n = len(final)
    fade_n = int(0.35 * SR)
    if n > fade_n:
        final[-fade_n:] *= np.linspace(1.0, 0.0, fade_n) ** 1.3
    parts.append(final)
    return concat_phrase(parts, 0.04, 0.1)


def report(path: Path) -> str:
    x, sr = sf.read(str(path))
    if x.ndim > 1:
        x = x.mean(1)
    peak = float(np.max(np.abs(x))) + 1e-12
    dbfs = 20 * math.log10(peak)
    dur = len(x) / sr
    return f"{path.name}: {dur:.3f}s  peak {dbfs:.2f} dBFS"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = [
        ("trombone_bureaucratic_medium_v1.wav", phrase_trombone_bureaucratic),
        ("trombone_dismissive_medium_v1.wav", phrase_trombone_dismissive),
        ("violin_cautious_medium_v1.wav", phrase_violin_cautious),
        ("violin_weary_medium_v1.wav", phrase_violin_weary),
    ]
    lines = []
    for name, fn in jobs:
        print(f"Building {name} ...")
        audio = fn()
        # ensure duration in 1.8–2.5 by light pad/trim if needed
        dur = len(audio) / SR
        if dur < 1.8:
            audio = np.concatenate([audio, silence(1.85 - dur)])
        elif dur > 2.55:
            # fade early and trim
            keep = int(2.45 * SR)
            audio = audio[:keep]
            audio = fade(audio, 3.0, 40.0)
        out = OUT / name
        write_wav(out, audio)
        lines.append(report(out))
        print(" ", lines[-1])
    print("\n".join(lines))


if __name__ == "__main__":
    main()
