#!/usr/bin/env python3
"""
Build Peanuts-style trombone/violin voice audition via expressive MIDI + FluidSynth.

Proper notes through MuseScore General (Full) — not Iowa grain concat, not additive synth.
"""
from __future__ import annotations

import json
import math
import os
import struct
import subprocess
import sys
import wave
from pathlib import Path

from mido import Message, MetaMessage, MidiFile, MidiTrack, bpm2tempo

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "audition_midi"
SOUNDFONT = Path(
    os.environ.get(
        "VOICE_SOUNDFONT",
        "/usr/share/sounds/sf3/MuseScore_General_Full.sf3",
    )
)
FALLBACK_SF = Path("/usr/share/sounds/sf2/FluidR3_GM.sf2")
FLUIDSYNTH = "/usr/bin/fluidsynth"
SAMPLE_RATE = 44100
GAIN = os.environ.get("VOICE_FLUID_GAIN", "0.85")

# GM program numbers (0-based PC)
PROG_MUTED_TROMBONE = 58  # GM 59 Muted Trombone
PROG_TROMBONE = 56        # GM 57 Trombone
PROG_VIOLIN = 40          # GM 41 Violin

PB_CENTER = 8192


def ms_to_ticks(ms: float, tempo_bpm: float, tpq: int = 480) -> int:
    ms_per_beat = 60000.0 / tempo_bpm
    return max(0, int(round((ms / ms_per_beat) * tpq)))


def pb_signed(semitones: float, bend_range: float = 2.0) -> int:
    frac = max(-1.0, min(1.0, semitones / bend_range))
    return int(round(frac * 8191))


def build_phrase(path: Path, program: int, events: list[dict], tempo_bpm: float = 100.0):
    """
    Absolute-timeline builder.
    events: sequence of syllable dicts with absolute-ish sequential timing via dur/gap.
    Each: note, vel, dur_ms, gap_after_ms, bend_in, bend_out, expr_start, expr_end,
          optional trail_fade, cut_off, mod (CC1)
    """
    mid = MidiFile(ticks_per_beat=480)
    tr = MidiTrack()
    mid.tracks.append(tr)
    tr.append(MetaMessage("set_tempo", tempo=bpm2tempo(tempo_bpm)))
    tr.append(MetaMessage("track_name", name=path.stem, time=0))

    # Pitch bend sensitivity ±2
    for ctrl, val in [(101, 0), (100, 0), (6, 2), (38, 0)]:
        tr.append(Message("control_change", control=ctrl, value=val, time=0))

    tr.append(Message("program_change", program=program, time=0))
    tr.append(Message("control_change", control=7, value=110, time=0))   # channel volume
    tr.append(Message("control_change", control=11, value=100, time=0))  # expression
    tr.append(Message("control_change", control=1, value=0, time=0))
    tr.append(Message("pitchwheel", pitch=0, time=0))

    # lead-in
    t_accum = ms_to_ticks(50, tempo_bpm)

    for syl in events:
        note = int(syl["note"])
        vel = int(syl["vel"])
        dur = float(syl["dur_ms"])
        gap = float(syl.get("gap_after_ms", 50))
        b_in = float(syl.get("bend_in", 0.0))
        b_out = float(syl.get("bend_out", 0.0))
        e0 = int(syl.get("expr_start", 95))
        e1 = int(syl.get("expr_end", e0))
        mod = int(syl.get("mod", 0))
        trail = bool(syl.get("trail_fade", False))
        cut = bool(syl.get("cut_off", False))

        # start note
        tr.append(Message("control_change", control=11, value=e0, time=t_accum))
        t_accum = 0
        if mod:
            tr.append(Message("control_change", control=1, value=mod, time=0))
        tr.append(Message("pitchwheel", pitch=pb_signed(b_in), time=0))
        tr.append(Message("note_on", note=note, velocity=vel, time=0))

        if trail:
            # N steps of fade + droop across full duration
            n_steps = 6
            step = dur / n_steps
            for s in range(1, n_steps + 1):
                frac = s / n_steps
                expr = int(e0 + (e1 - e0) * frac)
                bend = b_in + (b_out - b_in) * frac
                tr.append(Message("control_change", control=11, value=expr, time=ms_to_ticks(step, tempo_bpm)))
                tr.append(Message("pitchwheel", pitch=pb_signed(bend), time=0))
            tr.append(Message("note_off", note=note, velocity=0, time=0))
        else:
            # half-way articulation
            half = dur * 0.5
            tr.append(Message("control_change", control=11, value=(e0 + e1) // 2, time=ms_to_ticks(half, tempo_bpm)))
            tr.append(Message("pitchwheel", pitch=pb_signed((b_in + b_out) / 2), time=0))
            tr.append(Message("control_change", control=11, value=e1, time=ms_to_ticks(dur - half, tempo_bpm)))
            tr.append(Message("pitchwheel", pitch=pb_signed(b_out), time=0))
            tr.append(Message("note_off", note=note, velocity=50 if cut else 24, time=0))

        # reset bend / mod between syllables
        tr.append(Message("pitchwheel", pitch=0, time=0))
        if mod:
            tr.append(Message("control_change", control=1, value=0, time=0))

        # gap / breath (advance time)
        t_accum = ms_to_ticks(gap, tempo_bpm)

    # end pad for release
    tr.append(Message("control_change", control=11, value=0, time=t_accum + ms_to_ticks(40, tempo_bpm)))
    tr.append(Message("control_change", control=123, value=0, time=0))  # all notes off
    tr.append(MetaMessage("end_of_track", time=ms_to_ticks(120, tempo_bpm)))
    mid.save(path)
    return mid.length


# ---- Styles (target ~2.0–2.3 s of speech content before pad) ----

def bureaucratic():
    # Measured, even, flatter — muted trombone mid-staff ~ F3–A3 (~2.1s)
    return [
        {"note": 53, "vel": 92, "dur_ms": 210, "gap_after_ms": 85, "bend_in": -0.06, "bend_out": 0.02, "expr_start": 88, "expr_end": 95},
        {"note": 53, "vel": 88, "dur_ms": 185, "gap_after_ms": 80, "bend_in": 0.0, "bend_out": 0.04, "expr_start": 86, "expr_end": 92},
        {"note": 55, "vel": 94, "dur_ms": 220, "gap_after_ms": 110, "bend_in": -0.08, "bend_out": 0.0, "expr_start": 92, "expr_end": 98},
        {"note": 53, "vel": 86, "dur_ms": 175, "gap_after_ms": 75, "bend_in": 0.02, "bend_out": -0.04, "expr_start": 84, "expr_end": 88},
        {"note": 55, "vel": 90, "dur_ms": 195, "gap_after_ms": 90, "bend_in": 0.05, "bend_out": 0.0, "expr_start": 90, "expr_end": 94},
        {"note": 55, "vel": 87, "dur_ms": 160, "gap_after_ms": 70, "bend_in": 0.0, "bend_out": -0.03, "expr_start": 86, "expr_end": 90},
        {"note": 53, "vel": 84, "dur_ms": 250, "gap_after_ms": 35, "bend_in": 0.0, "bend_out": -0.08, "expr_start": 88, "expr_end": 70},
    ]


def dismissive():
    # Short notes, falling contour, abrupt end (content ~2.1s so trim stays ≥1.8s)
    return [
        {"note": 60, "vel": 108, "dur_ms": 100, "gap_after_ms": 80, "bend_in": 0.12, "bend_out": -0.05, "expr_start": 110, "expr_end": 100},
        {"note": 58, "vel": 102, "dur_ms": 88, "gap_after_ms": 75, "bend_in": 0.05, "bend_out": -0.12, "expr_start": 105, "expr_end": 95},
        {"note": 55, "vel": 100, "dur_ms": 105, "gap_after_ms": 95, "bend_in": 0.0, "bend_out": -0.18, "expr_start": 102, "expr_end": 88},
        {"note": 53, "vel": 94, "dur_ms": 92, "gap_after_ms": 260, "bend_in": -0.05, "bend_out": -0.15, "expr_start": 95, "expr_end": 78},
        {"note": 57, "vel": 104, "dur_ms": 85, "gap_after_ms": 70, "bend_in": 0.08, "bend_out": -0.1, "expr_start": 108, "expr_end": 92},
        {"note": 55, "vel": 100, "dur_ms": 98, "gap_after_ms": 75, "bend_in": 0.0, "bend_out": -0.18, "expr_start": 100, "expr_end": 86},
        {"note": 52, "vel": 96, "dur_ms": 115, "gap_after_ms": 70, "bend_in": -0.04, "bend_out": -0.22, "expr_start": 96, "expr_end": 80},
        {"note": 50, "vel": 94, "dur_ms": 125, "gap_after_ms": 60, "bend_in": -0.05, "bend_out": -0.3, "expr_start": 94, "expr_end": 70},
        {"note": 48, "vel": 114, "dur_ms": 72, "gap_after_ms": 40, "bend_in": -0.12, "bend_out": -0.45, "expr_start": 120, "expr_end": 25, "cut_off": True},
        {"note": 46, "vel": 98, "dur_ms": 48, "gap_after_ms": 15, "bend_in": -0.25, "bend_out": -0.55, "expr_start": 90, "expr_end": 10, "cut_off": True},
    ]


def cautious():
    # Slower, pauses, small pitch moves — violin ~ C4–D4
    return [
        {"note": 60, "vel": 95, "dur_ms": 240, "gap_after_ms": 140, "bend_in": -0.04, "bend_out": 0.03, "expr_start": 85, "expr_end": 95, "mod": 8},
        {"note": 62, "vel": 90, "dur_ms": 200, "gap_after_ms": 120, "bend_in": 0.0, "bend_out": 0.06, "expr_start": 88, "expr_end": 96},
        {"note": 62, "vel": 98, "dur_ms": 260, "gap_after_ms": 160, "bend_in": -0.05, "bend_out": 0.0, "expr_start": 90, "expr_end": 100},
        {"note": 60, "vel": 88, "dur_ms": 180, "gap_after_ms": 110, "bend_in": 0.04, "bend_out": -0.03, "expr_start": 82, "expr_end": 90},
        {"note": 61, "vel": 92, "dur_ms": 210, "gap_after_ms": 130, "bend_in": 0.0, "bend_out": 0.05, "expr_start": 86, "expr_end": 92, "mod": 6},
        {"note": 60, "vel": 85, "dur_ms": 250, "gap_after_ms": 50, "bend_in": 0.02, "bend_out": -0.06, "expr_start": 88, "expr_end": 65},
    ]


def weary():
    # Drooping contour, trailing fade on last (~2.2s)
    return [
        {"note": 64, "vel": 98, "dur_ms": 230, "gap_after_ms": 95, "bend_in": 0.06, "bend_out": -0.1, "expr_start": 95, "expr_end": 82, "mod": 12},
        {"note": 62, "vel": 92, "dur_ms": 210, "gap_after_ms": 85, "bend_in": 0.0, "bend_out": -0.14, "expr_start": 90, "expr_end": 75},
        {"note": 60, "vel": 88, "dur_ms": 240, "gap_after_ms": 100, "bend_in": -0.05, "bend_out": -0.18, "expr_start": 85, "expr_end": 70},
        {"note": 58, "vel": 82, "dur_ms": 220, "gap_after_ms": 80, "bend_in": 0.0, "bend_out": -0.22, "expr_start": 80, "expr_end": 62},
        {
            "note": 55,
            "vel": 78,
            "dur_ms": 600,
            "gap_after_ms": 15,
            "bend_in": -0.12,
            "bend_out": -0.75,
            "expr_start": 75,
            "expr_end": 10,
            "trail_fade": True,
            "mod": 18,
        },
    ]


CLIPS = [
    {"stem": "trombone_bureaucratic_medium_v1", "program": PROG_MUTED_TROMBONE,
     "program_name": "Muted Trombone (GM #59, PC 58)", "tempo": 100, "make": bureaucratic},
    {"stem": "trombone_dismissive_medium_v1", "program": PROG_MUTED_TROMBONE,
     "program_name": "Muted Trombone (GM #59, PC 58)", "tempo": 112, "make": dismissive},
    {"stem": "violin_cautious_medium_v1", "program": PROG_VIOLIN,
     "program_name": "Violin (GM #41, PC 40)", "tempo": 92, "make": cautious},
    {"stem": "violin_weary_medium_v1", "program": PROG_VIOLIN,
     "program_name": "Violin (GM #41, PC 40)", "tempo": 86, "make": weary},
]


def resolve_soundfont() -> Path:
    if SOUNDFONT.exists():
        return SOUNDFONT
    lite = Path("/usr/share/sounds/sf3/MuseScore_General_Lite.sf3")
    if lite.exists():
        print(f"WARNING: using Lite soundfont {lite}")
        return lite
    if FALLBACK_SF.exists():
        print(f"WARNING: falling back to FluidR3 {FALLBACK_SF}")
        return FALLBACK_SF
    raise FileNotFoundError("No usable soundfont found")


def render_midi(sf: Path, mid_path: Path, wav_raw: Path):
    cmd = [
        FLUIDSYNTH, "-ni",
        "-F", str(wav_raw),
        "-r", str(SAMPLE_RATE),
        "-g", GAIN,
        "-o", "synth.chorus.active=0",
        "-o", "synth.reverb.active=0",
        str(sf), str(mid_path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not wav_raw.exists():
        raise RuntimeError(f"fluidsynth failed ({r.returncode}): {r.stderr}")


def read_wav_mono(path: Path):
    with wave.open(str(path), "rb") as w:
        ch, sw, rate, nframes, _, _ = w.getparams()
        raw = w.readframes(nframes)
    if sw != 2:
        raise ValueError("expected 16-bit")
    samples = struct.unpack(f"<{nframes * ch}h", raw)
    if ch == 2:
        mono = [(samples[i] + samples[i + 1]) // 2 for i in range(0, len(samples), 2)]
    else:
        mono = list(samples)
    return rate, mono


def write_wav_mono(path: Path, rate: int, mono: list[int]):
    mono = [max(-32767, min(32767, int(s))) for s in mono]
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack(f"<{len(mono)}h", *mono))


def postprocess(wav_raw: Path, wav_out: Path, target_peak_db: float = -4.5) -> dict:
    rate, mono = read_wav_mono(wav_raw)
    # Find content bounds with a low threshold (violin is soft in bank)
    abs_samp = [abs(s) for s in mono]
    peak_all = max(abs_samp) if abs_samp else 1
    thresh = max(80, int(peak_all * 0.02))  # 2% of peak or floor

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
    # pad 12 ms lead, 40 ms trail
    pad_pre = int(rate * 0.012)
    pad_post = int(rate * 0.070)
    start = max(0, start - pad_pre)
    end = min(len(mono) - 1, end + pad_post)
    clipped = mono[start : end + 1]

    # Soft edge fades
    fade_in = int(rate * 0.006)
    fade_out = int(rate * 0.020)
    for i in range(min(fade_in, len(clipped))):
        clipped[i] = int(clipped[i] * (i / fade_in))
    for i in range(min(fade_out, len(clipped))):
        idx = len(clipped) - 1 - i
        clipped[idx] = int(clipped[idx] * (i / fade_out) if False else clipped[idx] * ((fade_out - i) / fade_out))

    peak = max(abs(s) for s in clipped) if clipped else 1
    target = 10 ** (target_peak_db / 20.0) * 32767
    scale = target / peak if peak else 1.0
    scaled = [int(s * scale) for s in clipped]
    write_wav_mono(wav_out, rate, scaled)

    peak2 = max(abs(s) for s in scaled) / 32768.0
    peak_db = 20 * math.log10(peak2) if peak2 > 0 else -99
    dur = len(scaled) / float(rate)
    return {"duration_s": round(dur, 3), "peak_dbfs": round(peak_db, 2)}


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sf = resolve_soundfont()
    report = {
        "soundfont": str(sf.resolve()),
        "fluidsynth": FLUIDSYNTH,
        "gain": GAIN,
        "reverb": False,
        "chorus": False,
        "clips": [],
    }

    for clip in CLIPS:
        stem = clip["stem"]
        syl = clip["make"]()
        mid_path = OUT_DIR / f"{stem}.mid"
        raw_path = OUT_DIR / f"{stem}.raw.wav"
        wav_path = OUT_DIR / f"{stem}.wav"

        length = build_phrase(mid_path, clip["program"], syl, tempo_bpm=clip["tempo"])
        render_midi(sf, mid_path, raw_path)
        # Slightly hotter target for quieter violin bank layers
        target = -4.0 if "violin" in stem else -4.5
        stats = postprocess(raw_path, wav_path, target_peak_db=target)
        raw_path.unlink(missing_ok=True)

        entry = {
            "file": wav_path.name,
            "midi": mid_path.name,
            "program": clip["program"],
            "program_name": clip["program_name"],
            "tempo_bpm": clip["tempo"],
            "n_syllables": len(syl),
            "midi_length_s": round(length, 3),
            **stats,
        }
        report["clips"].append(entry)
        print(f"{stem}: {stats['duration_s']}s  peak={stats['peak_dbfs']} dBFS  "
              f"midi={length:.2f}s  prog={clip['program']}  syl={len(syl)}")

    (OUT_DIR / "render_report.json").write_text(json.dumps(report, indent=2))
    print("soundfont:", sf)
    return report


if __name__ == "__main__":
    main()
