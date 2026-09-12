# Three Colors of Madness — Voice Pack

Wordless instrumental speech in the Peanuts adult-voice register for
*Three Colors of Madness*: musicians speaking through trombone (primary)
and violin (alternate). No intelligible words.

## Current status

**Placeholder library is built.** Production method is expressive MIDI
through MuseScore General Full via FluidSynth (muted trombone + violin).
Quality can improve later by editing individual `library/midi/*.mid`
files and re-rendering.

144 clips live in `library/`:

- instruments: `trombone`, `violin`
- 12 styles: neutral, bureaucratic, dismissive, cautious, questioning,
  weary, angry, alarmed, haunting, happy, conspiratorial, pleading
- lengths: short / medium / long
- two distinct takes: `v1`, `v2`

Naming: `{instrument}_{style}_{length}_v{1|2}.wav`

Examples: `trombone_angry_short_v1.wav`,
`trombone_bureaucratic_medium_v2.wav`, `violin_haunting_long_v1.wav`

Matching MIDI sources: `library/midi/{same-basename}.mid`
Index + render metadata: `library/manifest.json`

## Audio spec

- Mono WAV, 44.1 kHz, 16-bit PCM
- Peak normalized ≈ −4.5 dBFS (violin ≈ −4.0); no clipping
- FluidSynth reverb/chorus off (no long tails)
- ~50–60 ms silence pad at start and end
- Speech-like phrasing (irregular syllables, pauses, stress) — not
  melodies, fanfares, or cadences

| Length | Listen target | Validator band |
|--------|---------------|----------------|
| short  | ~0.7–1.2 s    | 0.55–1.35 s    |
| medium | ~1.5–2.5 s    | 1.35–2.70 s    |
| long   | ~3–4.5 s      | 2.80–4.80 s    |

Programs: Muted Trombone GM #59 (PC 58), Violin GM #41 (PC 40).

## Rebuild / validate

```bash
python3 build_midi_library.py          # render all 144 + validate
python3 build_midi_library.py --validate
python3 validate_library.py
python3 build_midi_library.py --only trombone_angry_short_v1
```

Requires FluidSynth, MuseScore General Full (`VOICE_SOUNDFONT` override),
and Python `mido` + `numpy`. Env: `VOICE_SOUNDFONT`, `VOICE_FLUID_GAIN`.

The four approved MIDI-audition phrases are reused for the matching
library slots (`trombone_bureaucratic_medium_v1`,
`trombone_dismissive_medium_v1`, `violin_cautious_medium_v1`,
`violin_weary_medium_v1`).

## Earlier gates (kept, do not delete)

| Folder | Method | Status |
|--------|--------|--------|
| `audition_midi/` | MuseScore MIDI / FluidSynth (4-clip listen) | approved path |
| `audition_orchestral/` | Iowa MIS grain concat | rejected this round |
| `audition/` | additive synth | rejected earlier |

```bash
python3 build_midi_audition.py        # regenerate the 4-clip MIDI gate
```

## Credits

MuseScore General soundfont (MIT) + FluidSynth — see `CREDITS.md`.
