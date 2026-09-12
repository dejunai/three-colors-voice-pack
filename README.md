# Three Colors of Madness — Voice Pack (WIP)

Wordless instrumental speech in the Peanuts adult-voice register for
*Three Colors of Madness*: musicians speaking through trombone (primary)
and violin (alternate). No intelligible words.

## Current status

**MIDI audition (user-chosen next gate):** expressive MIDI into MuseScore
General Full via FluidSynth (proper notes / sample bank). Iowa MIS grain
concat was rejected as still too synthetic/effect-like.

| File | Style |
|------|--------|
| `audition_midi/trombone_bureaucratic_medium_v1.wav` | practiced official wording |
| `audition_midi/trombone_dismissive_medium_v1.wav` | brushing aside |
| `audition_midi/violin_cautious_medium_v1.wav` | carefully measured |
| `audition_midi/violin_weary_medium_v1.wav` | tired trailing cadence |

Matching `.mid` files sit next to each WAV. Details: `audition_midi/README.md`.

Do not expand the full style/length library until these pass an
“unmistakably trombone/violin playing” listen.

Prior packs kept for reference only:

- `audition_orchestral/` — Iowa MIS grains (rejected this round)
- `audition/` — additive synth (rejected earlier)

## Spec (target library)

- Delivery styles: see project brief
- Lengths: short / medium / long × 2 takes
- Plus short conversational reactions
- Mono WAV, 44.1 kHz, 16-bit PCM, dry
- Naming: `trombone_guarded_medium_v1.wav`

## Build

```bash
python3 build_midi_audition.py
```

Requires FluidSynth, MuseScore General soundfont (or `VOICE_SOUNDFONT`),
ffmpeg, and Python mido.

## Credits

MuseScore General soundfont (MIT) + FluidSynth — see `CREDITS.md`.
