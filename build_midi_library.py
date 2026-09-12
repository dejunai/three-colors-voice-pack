#!/usr/bin/env python3
"""
Build the complete placeholder instrumental-speech library.

144 mono WAVs: trombone|violin × 12 styles × short|medium|long × v1|v2
plus matching MIDI under library/midi/ and library/manifest.json.

Production path (same as build_midi_audition.py):
  expressive MIDI → MuseScore General Full SF3 → FluidSynth (reverb/chorus OFF)

    python3 build_midi_library.py
    python3 build_midi_library.py --validate
    python3 build_midi_library.py --only trombone_angry_short_v1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import struct
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

import build_midi_audition as audition

ROOT = Path(__file__).resolve().parent
LIB_DIR = ROOT / "library"
MIDI_DIR = LIB_DIR / "midi"
SAMPLE_RATE = audition.SAMPLE_RATE

INSTRUMENTS = ("trombone", "violin")
STYLES = (
    "neutral",
    "bureaucratic",
    "dismissive",
    "cautious",
    "questioning",
    "weary",
    "angry",
    "alarmed",
    "haunting",
    "happy",
    "conspiratorial",
    "pleading",
)
LENGTHS = ("short", "medium", "long")
TAKES = (1, 2)

# Validation / design bands (seconds)
BANDS = {
    "short": (0.55, 1.35),
    "medium": (1.35, 2.70),
    "long": (2.80, 4.80),
}
# Aim near the middle of the *desired* listen length, inside the allowed band
TARGET_S = {
    "short": 0.95,
    "medium": 2.00,
    "long": 3.55,
}

PROG = {
    "trombone": {
        "program": audition.PROG_MUTED_TROMBONE,
        "program_name": "Muted Trombone (GM #59, PC 58)",
        "center": 53,  # F3
        "lo": 48,
        "hi": 65,
    },
    "violin": {
        "program": audition.PROG_VIOLIN,
        "program_name": "Violin (GM #41, PC 40)",
        "center": 64,  # E4
        "lo": 55,
        "hi": 76,
    },
}

# Reuse the four approved audition phrases where they match a library slot
AUDITION_REUSE = {
    ("trombone", "bureaucratic", "medium", 1): (audition.bureaucratic, 100),
    ("trombone", "dismissive", "medium", 1): (audition.dismissive, 112),
    ("violin", "cautious", "medium", 1): (audition.cautious, 92),
    ("violin", "weary", "medium", 1): (audition.weary, 86),
}

N_SYL = {
    ("short", 1): 4,
    ("short", 2): 5,
    ("medium", 1): 7,
    ("medium", 2): 8,
    ("long", 1): 11,
    ("long", 2): 13,
}

# Speech-like pitch shapes (semitone offsets). v1 / v2 are different phrases.
SHAPES = {
    "gentle_fall": {
        1: [1, 2, 0, 1, -1, 0, -2, -1, -3, -2, -4, -3, -5],
        2: [0, -1, 2, 0, 1, -2, 0, -3, -1, -4, -2, -3, -5],
    },
    "flat": {
        1: [0, 0, 2, 0, 2, 0, 0, 2, 2, 0, 0, 2, 0],
        2: [2, 0, 0, 2, 0, 0, 2, 0, 2, 0, 0, 0, 2],
    },
    "fall_steep": {
        1: [5, 3, 2, 0, -1, 2, 0, -2, -4, -5, -6, -7, -8],
        2: [4, 5, 2, 3, 0, -2, 1, -3, -4, -6, -5, -7, -8],
    },
    "small": {
        1: [0, 1, 1, 0, 2, 1, 0, 1, 0, -1, 0, 1, 0],
        2: [1, 0, 0, 2, 1, 2, 0, 1, -1, 0, 1, 0, -1],
    },
    "rise_end": {
        1: [0, 1, -1, 0, 2, 0, 1, 2, 3, 2, 4, 5, 6],
        2: [1, 0, 2, -1, 1, 0, 3, 1, 2, 4, 3, 5, 7],
    },
    "droop": {
        1: [3, 2, 1, 2, 0, -1, -2, -1, -3, -4, -5, -6, -7],
        2: [2, 3, 0, 1, -1, 0, -3, -2, -4, -5, -4, -6, -8],
    },
    "wide": {
        1: [0, 5, -2, 4, -3, 6, 1, -4, 5, -2, 3, -5, 2],
        2: [4, -3, 6, 0, -4, 5, -2, 7, -3, 2, -5, 4, -6],
    },
    "broken": {
        1: [4, 4, 6, 2, 5, 5, 7, 3, 6, 2, 8, 4, 3],
        2: [3, 6, 6, 4, 7, 2, 5, 8, 3, 7, 7, 4, 9],
    },
    "eerie": {
        1: [0, 1, -2, 3, 0, -3, 2, -1, 4, -4, 1, -2, 0],
        2: [2, -3, 0, 4, -1, -4, 1, 3, -2, 0, -5, 2, -3],
    },
    "buoyant": {
        1: [0, 2, 1, 3, 2, 4, 1, 3, 2, 4, 3, 2, 4],
        2: [1, 3, 0, 2, 4, 2, 3, 1, 4, 2, 5, 3, 4],
    },
    "cluster": {
        1: [0, 1, 0, -1, 0, 1, -2, -1, 0, -1, -2, 0, -3],
        2: [-1, 0, 0, 1, -1, -2, 0, -1, 1, 0, -2, -1, -3],
    },
    "plead": {
        1: [0, 2, 1, 3, 0, 2, 4, 2, 3, 5, 2, 4, 3],
        2: [1, 3, 0, 2, 4, 1, 3, 5, 2, 4, 6, 3, 5],
    },
}

PROFILES = {
    "neutral": dict(
        tempo=100, vel=(86, 100), expr=(84, 102), dur=(120, 195), gap=(50, 95),
        bend_in=(-0.10, 0.08), bend_out=(-0.14, 0.05), mod=0,
        center_off_tb=0, center_off_vn=0, contour="gentle_fall", last="fall",
        quiet=False, force=False, tremolo=False,
    ),
    "bureaucratic": dict(
        tempo=96, vel=(84, 96), expr=(82, 98), dur=(155, 220), gap=(70, 110),
        bend_in=(-0.06, 0.05), bend_out=(-0.08, 0.04), mod=0,
        center_off_tb=0, center_off_vn=-1, contour="flat", last="tidy",
        quiet=False, force=False, tremolo=False,
    ),
    "dismissive": dict(
        tempo=114, vel=(94, 114), expr=(88, 118), dur=(70, 125), gap=(55, 95),
        bend_in=(-0.08, 0.14), bend_out=(-0.45, -0.08), mod=0,
        center_off_tb=2, center_off_vn=1, contour="fall_steep", last="cut",
        quiet=False, force=True, tremolo=False,
    ),
    "cautious": dict(
        tempo=82, vel=(80, 96), expr=(78, 98), dur=(160, 250), gap=(100, 170),
        bend_in=(-0.06, 0.06), bend_out=(-0.07, 0.06), mod=8,
        center_off_tb=-1, center_off_vn=0, contour="small", last="fall",
        quiet=False, force=False, tremolo=False,
    ),
    "questioning": dict(
        tempo=98, vel=(86, 102), expr=(84, 108), dur=(115, 200), gap=(55, 100),
        bend_in=(-0.08, 0.10), bend_out=(-0.05, 0.35), mod=0,
        center_off_tb=1, center_off_vn=1, contour="rise_end", last="rise",
        quiet=False, force=False, tremolo=False,
    ),
    "weary": dict(
        tempo=78, vel=(72, 94), expr=(60, 92), dur=(170, 280), gap=(80, 130),
        bend_in=(-0.05, 0.08), bend_out=(-0.35, -0.05), mod=14,
        center_off_tb=-1, center_off_vn=-2, contour="droop", last="trail",
        quiet=True, force=False, tremolo=False,
    ),
    "angry": dict(
        tempo=120, vel=(104, 122), expr=(100, 124), dur=(70, 140), gap=(40, 85),
        bend_in=(-0.20, 0.15), bend_out=(-0.25, 0.08), mod=0,
        center_off_tb=3, center_off_vn=2, contour="wide", last="cut",
        quiet=False, force=True, tremolo=False,
    ),
    "alarmed": dict(
        tempo=126, vel=(106, 124), expr=(100, 126), dur=(55, 120), gap=(30, 90),
        bend_in=(-0.12, 0.18), bend_out=(-0.15, 0.10), mod=20,
        center_off_tb=4, center_off_vn=3, contour="broken", last="cut",
        quiet=False, force=True, tremolo=True,
    ),
    "haunting": dict(
        tempo=70, vel=(68, 88), expr=(58, 90), dur=(180, 320), gap=(90, 180),
        bend_in=(-0.25, 0.20), bend_out=(-0.30, 0.15), mod=22,
        center_off_tb=-2, center_off_vn=-1, contour="eerie", last="trail",
        quiet=True, force=False, tremolo=True,
    ),
    "happy": dict(
        tempo=108, vel=(90, 110), expr=(90, 114), dur=(100, 175), gap=(45, 85),
        bend_in=(-0.08, 0.16), bend_out=(-0.06, 0.14), mod=0,
        center_off_tb=3, center_off_vn=3, contour="buoyant", last="lift",
        quiet=False, force=False, tremolo=False,
    ),
    "conspiratorial": dict(
        tempo=88, vel=(66, 86), expr=(55, 88), dur=(80, 150), gap=(25, 55),
        bend_in=(-0.10, 0.06), bend_out=(-0.12, 0.05), mod=6,
        center_off_tb=-3, center_off_vn=-3, contour="cluster", last="fall",
        quiet=True, force=False, tremolo=False,
    ),
    "pleading": dict(
        tempo=86, vel=(80, 104), expr=(75, 110), dur=(130, 230), gap=(60, 120),
        bend_in=(-0.08, 0.22), bend_out=(-0.10, 0.28), mod=4,
        center_off_tb=0, center_off_vn=1, contour="plead", last="soften",
        quiet=False, force=False, tremolo=False,
    ),
}


def stem_name(instrument: str, style: str, length: str, take: int) -> str:
    return f"{instrument}_{style}_{length}_v{take}"


def expected_stems() -> list[tuple[str, str, str, int, str]]:
    out = []
    for inst in INSTRUMENTS:
        for style in STYLES:
            for length in LENGTHS:
                for take in TAKES:
                    out.append((inst, style, length, take, stem_name(inst, style, length, take)))
    return out


def rng_for(*parts) -> random.Random:
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return random.Random(int(h[:16], 16))


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _pick_contour(style: str, take: int, n: int, rng: random.Random) -> list[int]:
    key = PROFILES[style]["contour"]
    base = list(SHAPES[key][take])
    if len(base) >= n:
        start = 0 if take == 1 else min(1, len(base) - n)
        shape = base[start : start + n]
        if len(shape) < n:
            shape = base[:n]
    else:
        shape = list(base)
        while len(shape) < n:
            shape.append(base[len(shape) % len(base)] + rng.choice([-1, 0, 1]))
    # Break accidental 3-step scalar runs (avoid a little tune)
    for i in range(2, len(shape)):
        d1 = shape[i - 1] - shape[i - 2]
        d2 = shape[i] - shape[i - 1]
        if d1 == d2 and abs(d1) == 1:
            shape[i] = shape[i - 1] + rng.choice([-2, 0, 2])
    return shape


def _pause_indices(style: str, length: str, take: int, n: int) -> set[int]:
    pauses: set[int] = set()
    if length == "long":
        pauses.add(n // 2 - 1)
        if take == 2:
            pauses.add(max(1, n // 3 - 1))
    if length == "medium" and style in ("cautious", "conspiratorial", "pleading", "haunting", "weary"):
        pauses.add((n // 2 - 1) if take == 1 else max(1, n // 3 - 1))
    if style == "cautious":
        pauses.add(1 if take == 1 else min(2, n - 2))
    if style == "alarmed" and n > 4:
        pauses.add(2)
        if take == 2:
            pauses.add(min(4, n - 2))
    if style == "conspiratorial":
        step = 3 if take == 1 else 4
        for i in range(step - 1, n - 1, step):
            pauses.add(i)
    if style == "pleading" and n > 5:
        pauses.add(3 if take == 1 else 4)
    return {p for p in pauses if 0 <= p < n - 1}


def _pause_extra_ms(length: str, style: str, rng: random.Random) -> float:
    if length == "short":
        lo, hi = 55, 100
    elif length == "medium":
        lo, hi = 110, 190
    else:
        lo, hi = 200, 340
    if style == "cautious":
        lo += 30
        hi += 40
    if style == "alarmed":
        lo = max(40, lo - 40)
        hi = max(lo + 20, hi - 40)
    return rng.uniform(lo, hi)


def make_events(instrument: str, style: str, length: str, take: int):
    key = (instrument, style, length, take)
    if key in AUDITION_REUSE:
        fn, tempo = AUDITION_REUSE[key]
        return fn(), tempo

    rng = rng_for(instrument, style, length, take, "phrase")
    spec = PROFILES[style]
    n = N_SYL[(length, take)]
    contour = _pick_contour(style, take, n, rng)
    pauses = _pause_indices(style, length, take, n)
    meta = PROG[instrument]
    center = meta["center"] + (spec["center_off_tb"] if instrument == "trombone" else spec["center_off_vn"])
    # v2 sits a step away so phrasing/register differ, not just velocity
    if take == 2:
        center += rng.choice([-2, -1, 1, 2])

    stress_period = 2 if take == 1 else 3
    events = []
    for i in range(n):
        stressed = (i % stress_period) == (0 if take == 1 else 1)
        dur = rng.uniform(*spec["dur"])
        if stressed:
            dur *= 1.22
        gap = rng.uniform(*spec["gap"])
        if i in pauses:
            gap += _pause_extra_ms(length, style, rng)
        # last-syllable treatment
        last = i == n - 1
        last_kind = spec["last"]
        trail = False
        cut = False
        if last:
            if last_kind == "trail":
                dur = max(dur, 420 if length != "short" else 260)
                trail = True
                gap = rng.uniform(12, 28)
            elif last_kind == "cut":
                dur = min(dur, 90)
                cut = True
                gap = rng.uniform(12, 30)
            elif last_kind == "rise":
                dur *= 1.15
            elif last_kind == "tidy":
                dur *= 1.08
                gap = rng.uniform(20, 40)
            elif last_kind == "soften":
                dur *= 1.20
            elif last_kind == "lift":
                dur *= 1.05
            elif last_kind == "fall":
                dur *= 1.10

        vel = rng.randint(*spec["vel"])
        if spec["force"] and stressed:
            vel = min(127, vel + rng.randint(4, 10))
        if spec["quiet"]:
            vel = max(64, vel - 4)
        if last and last_kind in ("soften", "trail", "fall"):
            vel = max(64, vel - rng.randint(6, 14))

        e0 = rng.randint(*spec["expr"])
        e1 = rng.randint(*spec["expr"])
        if last and last_kind in ("trail", "soften"):
            e1 = max(8, min(e1, 36))
        if last and last_kind == "cut":
            e1 = max(8, min(e1, 28))
        if last and last_kind == "rise":
            e1 = min(124, max(e1, e0 + 8))

        b_in = rng.uniform(*spec["bend_in"])
        b_out = rng.uniform(*spec["bend_out"])
        if last and last_kind in ("fall", "trail", "cut"):
            b_out = min(b_out, -0.18) - rng.uniform(0.05, 0.22)
        if last and last_kind in ("rise", "lift"):
            b_out = max(b_out, 0.18) + rng.uniform(0.04, 0.16)

        note = _clamp(center + contour[i], meta["lo"], meta["hi"])
        ev = {
            "note": int(note),
            "vel": int(_clamp(vel, 1, 127)),
            "dur_ms": float(dur),
            "gap_after_ms": float(gap),
            "bend_in": float(b_in),
            "bend_out": float(b_out),
            "expr_start": int(_clamp(e0, 1, 127)),
            "expr_end": int(_clamp(e1, 1, 127)),
            "mod": int(spec["mod"]),
            "trail_fade": trail,
            "cut_off": cut,
            "stressed": stressed,
        }
        events.append(ev)

    events = _apply_instrument_flavor(events, instrument, style, take, rng)
    events = _maybe_tremolo(events, instrument, style, take, rng)
    events = _scale_to_target_ms(events, length, instrument)
    return events, spec["tempo"]


def _apply_instrument_flavor(events, instrument, style, take, rng):
    spec = PROFILES[style]
    if instrument == "trombone":
        for i, ev in enumerate(events):
            # Tongued attacks / mute scoops / falls
            if ev["dur_ms"] < 115 and rng.random() < (0.60 if spec["force"] else 0.28):
                ev["cut_off"] = True
            if i == 0 or ev.get("stressed"):
                ev["bend_in"] = _clamp(ev["bend_in"] - rng.uniform(0.10, 0.28), -1.8, 1.8)
            if style in ("dismissive", "weary", "angry", "neutral") or i == len(events) - 1:
                ev["bend_out"] = _clamp(ev["bend_out"] - rng.uniform(0.06, 0.24), -1.9, 1.8)
            # Breathier gaps on trombone (air)
            if ev["gap_after_ms"] > 40:
                ev["gap_after_ms"] += rng.uniform(4, 16)
    else:
        for i, ev in enumerate(events):
            # Bow-change gap (except tight conspiratorial clusters)
            if style != "conspiratorial":
                ev["gap_after_ms"] += rng.uniform(8, 24)
            if rng.random() < 0.40:
                ev["bend_in"] = _clamp(
                    ev["bend_in"] + rng.choice([-1.0, 1.0]) * rng.uniform(0.10, 0.26),
                    -1.8,
                    1.8,
                )
            ev["expr_start"] = int(_clamp(ev["expr_start"] + rng.randint(-8, 8), 20, 127))
            ev["expr_end"] = int(_clamp(ev["expr_end"] + rng.randint(-10, 8), 8, 127))
            if ev.get("mod", 0) == 0 and style in ("cautious", "weary", "haunting", "conspiratorial"):
                ev["mod"] = rng.randint(6, 18)
    return events


def _maybe_tremolo(events, instrument, style, take, rng):
    spec = PROFILES[style]
    if not spec["tremolo"]:
        return events
    # Alarmed: stuttered onset; haunting violin: one shiver, still speech-like
    if style == "alarmed":
        idx = 1 if take == 1 else min(2, len(events) - 1)
        reps = 3 if take == 1 else 4
    elif style == "haunting" and instrument == "violin":
        idx = 2 if len(events) > 3 else 1
        reps = 3
    else:
        return events
    base = events[idx]
    new = []
    for _ in range(reps):
        e = dict(base)
        e["dur_ms"] = rng.uniform(38, 56)
        e["gap_after_ms"] = rng.uniform(12, 24)
        e["vel"] = int(_clamp(base["vel"] + rng.randint(-4, 6), 70, 127))
        e["cut_off"] = True
        e["trail_fade"] = False
        new.append(e)
    new[-1]["gap_after_ms"] = base["gap_after_ms"]
    events[idx : idx + 1] = new
    return events


def _content_ms(events) -> float:
    return sum(float(e["dur_ms"]) + float(e.get("gap_after_ms", 0)) for e in events)


def _scale_to_target_ms(events, length, instrument):
    target = TARGET_S[length] * 1000.0
    # Leave a little room for pads + FluidSynth release that postprocess trims
    target *= 0.90
    cur = _content_ms(events)
    if cur < 1:
        return events
    scale = target / cur
    scale = _clamp(scale, 0.55, 1.85)
    min_dur = 58 if instrument == "trombone" else 78
    for e in events:
        if e.get("trail_fade"):
            e["dur_ms"] = max(220.0, e["dur_ms"] * scale)
        else:
            e["dur_ms"] = max(min_dur, e["dur_ms"] * scale)
        e["gap_after_ms"] = max(10.0, e["gap_after_ms"] * scale)
    return events


def scale_events(events, factor: float, instrument: str):
    min_dur = 58 if instrument == "trombone" else 78
    out = []
    for e in events:
        e = dict(e)
        if e.get("trail_fade"):
            e["dur_ms"] = max(200.0, e["dur_ms"] * factor)
        else:
            e["dur_ms"] = max(min_dur, e["dur_ms"] * factor)
        e["gap_after_ms"] = max(10.0, e.get("gap_after_ms", 40) * factor)
        out.append(e)
    return out


def postprocess(wav_raw: Path, wav_out: Path, target_peak_db: float = -4.5) -> dict:
    """Trim to content, 45–60 ms pads, fade edges, peak-normalize, mono 16-bit."""
    rate, mono = audition.read_wav_mono(wav_raw)
    abs_samp = [abs(s) for s in mono]
    peak_all = max(abs_samp) if abs_samp else 1
    thresh = max(80, int(peak_all * 0.02))

    def first_above(seq, thr):
        for i, v in enumerate(seq):
            if v >= thr:
                return i
        return 0

    def last_above(seq, thr):
        for i in range(len(seq) - 1, -1, -1):
            if seq[i] >= thr:
                return i
        return len(seq) - 1

    start = first_above(abs_samp, thresh)
    end = last_above(abs_samp, thresh)
    pad_pre = int(rate * 0.050)   # 50 ms
    pad_post = int(rate * 0.060)  # 60 ms
    start = max(0, start - pad_pre)
    end = min(len(mono) - 1, end + pad_post)
    clipped = mono[start : end + 1]

    fade_in = int(rate * 0.008)
    fade_out = int(rate * 0.018)
    for i in range(min(fade_in, len(clipped))):
        clipped[i] = int(clipped[i] * (i / fade_in))
    for i in range(min(fade_out, len(clipped))):
        idx = len(clipped) - 1 - i
        clipped[idx] = int(clipped[idx] * ((fade_out - i) / fade_out))

    peak = max(abs(s) for s in clipped) if clipped else 1
    target = 10 ** (target_peak_db / 20.0) * 32767
    scale = target / peak if peak else 1.0
    scaled = [int(s * scale) for s in clipped]
    # hard safety so we never write 32768-equivalent clip
    scaled = [max(-32767, min(32767, s)) for s in scaled]
    audition.write_wav_mono(wav_out, rate, scaled)

    peak2 = max(abs(s) for s in scaled) / 32768.0
    peak_db = 20 * math.log10(peak2) if peak2 > 0 else -99.0
    dur = len(scaled) / float(rate)
    return {
        "duration": round(dur, 4),
        "peak_level": round(peak_db, 2),
        "sample_rate": rate,
        "channels": 1,
    }


def render_clip(sf: Path, instrument: str, style: str, length: str, take: int) -> dict:
    stem = stem_name(instrument, style, length, take)
    events, tempo = make_events(instrument, style, length, take)
    mid_path = MIDI_DIR / f"{stem}.mid"
    wav_path = LIB_DIR / f"{stem}.wav"
    prog = PROG[instrument]
    target_db = -4.0 if instrument == "violin" else -4.5
    lo, hi = BANDS[length]
    target = TARGET_S[length]

    stats = None
    last_dur = None
    for attempt in range(6):
        audition.build_phrase(mid_path, prog["program"], events, tempo_bpm=tempo)
        fd, raw_name = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        raw_path = Path(raw_name)
        try:
            audition.render_midi(sf, mid_path, raw_path)
            stats = postprocess(raw_path, wav_path, target_peak_db=target_db)
        finally:
            raw_path.unlink(missing_ok=True)

        last_dur = stats["duration"]
        if lo <= last_dur <= hi:
            break
        # Retrim timings toward the target. Overshoot correction is conservative
        # because pads + release are not linear with note length.
        if last_dur < 0.05:
            break
        factor = target / last_dur
        # Don't explode on a near-silent first pass
        factor = _clamp(factor, 0.62, 1.70)
        events = scale_events(events, factor, instrument)

    if stats is None:
        raise RuntimeError(f"failed to render {stem}")

    entry = {
        "filename": wav_path.name,
        "instrument": instrument,
        "style": style,
        "length": length,
        "take": take,
        "duration": stats["duration"],
        "sample_rate": stats["sample_rate"],
        "channels": stats["channels"],
        "peak_level": stats["peak_level"],
        "source": f"library/midi/{stem}.mid",
        "render_method": (
            "expressive MIDI → MuseScore General Full SF3 via FluidSynth "
            "(reverb/chorus off); peak-normalized mono 44.1 kHz 16-bit PCM"
        ),
        "program": prog["program"],
        "program_name": prog["program_name"],
        "tempo_bpm": tempo,
        "n_syllables": len(events),
        "attempts": attempt + 1,
    }
    flag = "OK" if lo <= stats["duration"] <= hi else "OUT-OF-BAND"
    print(
        f"{stem}: {stats['duration']:.3f}s  peak={stats['peak_level']:.2f} dBFS  "
        f"syl={len(events)}  {flag}"
    )
    return entry


def _wav_params(path: Path):
    with wave.open(str(path), "rb") as w:
        ch, sw, rate, nframes, _, _ = w.getparams()
        raw = w.readframes(nframes)
    samples = struct.unpack(f"<{nframes * ch}h", raw)
    if ch == 2:
        mono = np.array([(samples[i] + samples[i + 1]) / 2.0 for i in range(0, len(samples), 2)], dtype=np.float64)
    else:
        mono = np.array(samples, dtype=np.float64)
    return ch, sw, rate, nframes, mono, raw


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    a = a.astype(np.float64)
    b = b.astype(np.float64)
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na < 1e-9 or nb < 1e-9:
        return 1.0
    a = a / na
    b = b / nb
    n = max(len(a), len(b))
    if len(a) < n:
        a = np.pad(a, (0, n - len(a)))
    if len(b) < n:
        b = np.pad(b, (0, n - len(b)))
    return float(np.dot(a, b))


def validate(lib_dir: Path | None = None, verbose: bool = True) -> bool:
    lib_dir = Path(lib_dir or LIB_DIR)
    midi_dir = lib_dir / "midi"
    expected = expected_stems()
    expected_wav = {s[4] + ".wav" for s in expected}
    expected_mid = {s[4] + ".mid" for s in expected}

    found_wav = {p.name for p in lib_dir.glob("*.wav")}
    found_mid = {p.name for p in midi_dir.glob("*.mid")} if midi_dir.is_dir() else set()

    missing_wav = sorted(expected_wav - found_wav)
    extra_wav = sorted(found_wav - expected_wav)
    missing_mid = sorted(expected_mid - found_mid)

    fmt_fail = []
    dur_fail = []
    clip_fail = []
    hashes: dict[str, str] = {}
    audio: dict[str, np.ndarray] = {}
    peaks: dict[str, float] = {}
    durs: dict[str, float] = {}

    for inst, style, length, take, stem in expected:
        wav = lib_dir / f"{stem}.wav"
        if not wav.exists():
            continue
        ch, sw, rate, nframes, mono, raw = _wav_params(wav)
        dur = nframes / float(rate)
        durs[stem] = dur
        hashes[stem] = hashlib.md5(raw).hexdigest()
        audio[stem] = mono
        peak = float(np.max(np.abs(mono))) / 32768.0 if len(mono) else 0.0
        peaks[stem] = 20 * math.log10(peak) if peak > 0 else -99.0

        if ch != 1 or sw != 2 or rate != 44100:
            fmt_fail.append(f"{stem}.wav  ch={ch} sw={sw} rate={rate}")
        lo, hi = BANDS[length]
        if not (lo <= dur <= hi):
            dur_fail.append(f"{stem}.wav  {dur:.3f}s  allowed {lo}-{hi}")
        if peak >= 1.0 or peaks[stem] >= 0.0:
            clip_fail.append(f"{stem}.wav  peak={peaks[stem]:.2f} dBFS")

    # byte-identical content (payload, not headers)
    by_hash: dict[str, list[str]] = {}
    for stem, h in hashes.items():
        by_hash.setdefault(h, []).append(stem)
    ident_pairs = [names for names in by_hash.values() if len(names) > 1]

    corr_fail = []
    corr_warn = []
    corrs = []
    for inst in INSTRUMENTS:
        for style in STYLES:
            for length in LENGTHS:
                a = f"{inst}_{style}_{length}_v1"
                b = f"{inst}_{style}_{length}_v2"
                if a in audio and b in audio:
                    c = _corr(audio[a], audio[b])
                    corrs.append((a, b, c))
                    if c > 0.985:
                        corr_fail.append(f"{a} vs {b}  corr={c:.4f}")
                    elif c > 0.92:
                        corr_warn.append(f"{a} vs {b}  corr={c:.4f}")

    n_ok_fmt = len(expected) - len(missing_wav) - len(fmt_fail)
    lines = []
    lines.append("=== Library validation ===")
    lines.append(f"Expected WAV: {len(expected_wav)}")
    lines.append(f"Found WAV:    {len(found_wav)}")
    lines.append(f"Missing WAV:  {len(missing_wav)}")
    lines.append(f"Unexpected:   {len(extra_wav)}")
    lines.append(f"Missing MIDI: {len(missing_mid)}")
    lines.append(f"Format fail (mono/44.1k/16-bit): {len(fmt_fail)}")
    lines.append(f"Duration fail: {len(dur_fail)}")
    lines.append(f"Clipping:      {len(clip_fail)}")
    lines.append(f"Byte-identical groups: {len(ident_pairs)}")
    lines.append(f"v1/v2 corr fail (>0.985): {len(corr_fail)}")
    lines.append(f"v1/v2 corr warn (>0.92):  {len(corr_warn)}")
    if corrs:
        cs = [c for _, _, c in corrs]
        lines.append(f"v1/v2 corr min/mean/max: {min(cs):.3f} / {sum(cs)/len(cs):.3f} / {max(cs):.3f}")
    if durs:
        lines.append(
            f"Duration range: {min(durs.values()):.3f}s – {max(durs.values()):.3f}s"
        )
    if peaks:
        lines.append(
            f"Peak range: {min(peaks.values()):.2f} – {max(peaks.values()):.2f} dBFS"
        )

    def dump(title, items, limit=40):
        if not items:
            return
        lines.append(f"-- {title} --")
        for x in items[:limit]:
            lines.append(f"  {x}")
        if len(items) > limit:
            lines.append(f"  ... +{len(items) - limit} more")

    dump("Missing WAV", missing_wav)
    dump("Unexpected WAV", extra_wav)
    dump("Missing MIDI", missing_mid)
    dump("Format", fmt_fail)
    dump("Duration", dur_fail)
    dump("Clipping", clip_fail)
    dump("Identical", ident_pairs)
    dump("High v1/v2 corr", corr_fail)
    dump("Corr warnings", corr_warn)

    failed = bool(
        missing_wav
        or extra_wav
        or missing_mid
        or fmt_fail
        or dur_fail
        or clip_fail
        or ident_pairs
        or corr_fail
    )
    lines.append("RESULT: FAIL" if failed else "RESULT: PASS")
    report = "\n".join(lines)
    if verbose:
        print(report)
    (lib_dir / "validation_report.txt").write_text(report + "\n")
    return not failed


def build(only: list[str] | None = None) -> dict:
    LIB_DIR.mkdir(parents=True, exist_ok=True)
    MIDI_DIR.mkdir(parents=True, exist_ok=True)
    sf = audition.resolve_soundfont()
    print(f"soundfont: {sf}")
    print(f"fluidsynth: {audition.FLUIDSYNTH}  gain={audition.GAIN}  reverb=off chorus=off")

    only_set = set(only) if only else None
    entries = []
    # Keep prior manifest entries when doing a partial rebuild
    manifest_path = LIB_DIR / "manifest.json"
    prior = {}
    if only_set and manifest_path.exists():
        try:
            old = json.loads(manifest_path.read_text())
            for e in old.get("clips", []):
                prior[e["filename"]] = e
        except Exception:
            prior = {}

    for inst, style, length, take, stem in expected_stems():
        if only_set and stem not in only_set:
            fn = f"{stem}.wav"
            if fn in prior:
                entries.append(prior[fn])
            continue
        entries.append(render_clip(sf, inst, style, length, take))

    # stable order
    order = {s[4] + ".wav": i for i, s in enumerate(expected_stems())}
    entries.sort(key=lambda e: order.get(e["filename"], 9999))

    report = {
        "soundfont": str(sf.resolve()),
        "fluidsynth": audition.FLUIDSYNTH,
        "gain": audition.GAIN,
        "reverb": False,
        "chorus": False,
        "sample_rate": SAMPLE_RATE,
        "bit_depth": 16,
        "channels": 1,
        "render_method": (
            "expressive MIDI → MuseScore General Full SF3 via FluidSynth "
            "(reverb/chorus off)"
        ),
        "n_clips": len(entries),
        "clips": entries,
    }
    manifest_path.write_text(json.dumps(report, indent=2) + "\n")
    print(f"wrote {manifest_path}  ({len(entries)} clips)")
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description="Build / validate the 144-clip voice library")
    p.add_argument("--validate", action="store_true", help="validate only, do not render")
    p.add_argument("--only", nargs="*", help="optional list of stems to (re)build")
    args = p.parse_args(argv)
    if args.validate:
        ok = validate()
        sys.exit(0 if ok else 1)
    build(only=args.only)
    ok = validate()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
