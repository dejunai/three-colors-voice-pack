# Trombone speech — first audition batch

Muted-trombone *adult voice* clips in the Peanuts animated-special register:
syllable pulses, pauses, breaths, emphasis, rising/falling inflection.
**No intelligible words.** Not melodies, punchlines, or stingers.

## Specs
- Instrument: trombone (muted / plunger-like)
- Length: medium (target 1.5–2.5 s)
- Format: mono WAV, 44.1 kHz, 16-bit PCM
- Peak: about −3 to −6 dBFS, no clipping
- Dry: no reverb tail, no bed music, no other instruments
- Clean edges: ~10 ms fade in/out

## Criteria (listen for)
- Sounds like talking, not a tune
- Each clip is one sentence-ish line (5–9 syllables, often a mid pause)
- Styles are distinct on playback:
  - **neutral** — plain conversational statement; even-ish rhythm, gentle terminal fall
  - **bureaucratic** — practiced official wording; measured pace, flatter contour, tidy ending
  - **dismissive** — brushing aside; shorter syllables, falling contour, abrupt finish
  - **cautious** — carefully measured disclosure; slower, more pauses, small pitch moves
  - **questioning** — ordinary question; rising terminal inflection (speech rise, not an up-lick)
  - **weary** — tired cadence; drooping pitch, longer final syllable fade
- v1 vs v2: different syllable count / pause placement / inflection, not a pitch shift

## Files

| File | Style | Take | Duration | Peak dBFS |
|------|-------|------|----------|-----------|
| `trombone_neutral_medium_v1.wav` | neutral | v1 | 1.94s | -4.5 |
| `trombone_neutral_medium_v2.wav` | neutral | v2 | 1.95s | -4.5 |
| `trombone_bureaucratic_medium_v1.wav` | bureaucratic | v1 | 2.12s | -4.5 |
| `trombone_bureaucratic_medium_v2.wav` | bureaucratic | v2 | 2.12s | -4.5 |
| `trombone_dismissive_medium_v1.wav` | dismissive | v1 | 1.78s | -4.5 |
| `trombone_dismissive_medium_v2.wav` | dismissive | v2 | 1.78s | -4.5 |
| `trombone_cautious_medium_v1.wav` | cautious | v1 | 2.26s | -4.5 |
| `trombone_cautious_medium_v2.wav` | cautious | v2 | 2.27s | -4.5 |
| `trombone_questioning_medium_v1.wav` | questioning | v1 | 1.98s | -4.5 |
| `trombone_questioning_medium_v2.wav` | questioning | v2 | 1.97s | -4.5 |
| `trombone_weary_medium_v1.wav` | weary | v1 | 2.30s | -4.5 |
| `trombone_weary_medium_v2.wav` | weary | v2 | 2.31s | -4.5 |

Regenerate this batch:

```
python3 /workspace/three-colors-voice-pack/synth_trombone_speech.py --audition
```
