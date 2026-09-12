# Three Colors of Madness — Voice Pack (WIP)

Wordless instrumental speech in the Peanuts adult-voice register for *Three Colors of Madness*: musicians speaking through trombone (primary) and violin (alternate). No intelligible words.

## Current status

**Orchestral audition (pass/fail gate):** Iowa MIS real samples, not additive synth.

| File | Style |
|------|--------|
| `audition_orchestral/trombone_bureaucratic_medium_v1.wav` | practiced official wording |
| `audition_orchestral/trombone_dismissive_medium_v1.wav` | brushing aside |
| `audition_orchestral/violin_cautious_medium_v1.wav` | carefully measured |
| `audition_orchestral/violin_weary_medium_v1.wav` | tired trailing cadence |

Do **not** expand the full style/length library until these pass an “unmistakably orchestral” listen.

Earlier additive-synth takes live under `audition/` for reference only (rejected as too electronic).

## Spec (target library)

- Delivery styles: see project brief (neutral, bureaucratic, dismissive, …)
- Lengths: short / medium / long × 2 takes
- Plus short conversational reactions
- Mono WAV, 44.1 kHz, 16-bit PCM, dry
- Naming: `trombone_guarded_medium_v1.wav`

## Build

```bash
python3 build_orchestral_audition.py
```

Requires ffmpeg, sox, rubberband-cli, and source files under `source_samples/` (see `CREDITS.md`).

## Credits

University of Iowa Musical Instrument Samples — see `CREDITS.md`.
