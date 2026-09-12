# MIDI audition — expressive trombone / violin (FluidSynth)

Peanuts-style wordless adult-voice takes: expressive MIDI through MuseScore General Full via FluidSynth (proper sample-bank notes). Not Iowa grain concat; not additive synth.

## Bank

| Field | Value |
|-------|--------|
| SoundFont | `/usr/share/sounds/sf3/MuseScore_General_Full.sf3` |
| Debian package | `musescore-general-soundfont` 0.2.1-1 (HQ / lossy SF3) |
| Symlink | `/usr/share/sounds/sf3/MuseScore_General.sf3` → Full |
| FluidSynth | `/usr/bin/fluidsynth`; reverb off, chorus off, `-g 0.85` |

### Programs used

| Clip | GM name | PC (0-based) | GM # |
|------|---------|--------------|------|
| trombones | Muted Trombone | 58 | 59 |
| violins | Violin | 40 | 41 |

Muted trombone for Peanuts-adjacent mute color without harsh DSP filters.

## Outputs

| File | Style |
|------|--------|
| `trombone_bureaucratic_medium_v1.wav` (+ `.mid`) | measured, even, flatter, tidy end |
| `trombone_dismissive_medium_v1.wav` (+ `.mid`) | short notes, falling, abrupt cut |
| `violin_cautious_medium_v1.wav` (+ `.mid`) | slower, pauses, small pitch moves |
| `violin_weary_medium_v1.wav` (+ `.mid`) | drooping pitch, trailing fade |

Spec: mono 44.1 kHz 16-bit PCM, dry, peak ~−3 to −6 dBFS, ~1.8–2.5 s. See `render_report.json`.

## MIDI craft

- Irregular short notes + gaps (tongued/bowed syllables), not equal 16ths
- Pitch bend (±2 semitone RPN) for lip-slur / portamento / weary droop
- CC11 Expression; light CC1 Mod on cautious/weary violin
- Velocity variation; dismissive hard cut-off
- Conversational F0: trombone ~F3–C4; violin ~C4–E4

## Rebuild

```bash
python3 /workspace/three-colors-voice-pack/build_midi_audition.py
```

Env: `VOICE_SOUNDFONT`, `VOICE_FLUID_GAIN`. Needs fluidsynth, ffmpeg, mido.

## Honest listen notes

Closer to instrument-playing-speech than Iowa grains. Mute trombone attacks read as brass; GM violin is legato-biased so consonants are limited. Not TV foley, but no beep-boop / grain smear. Iterate via matching `.mid` files.
