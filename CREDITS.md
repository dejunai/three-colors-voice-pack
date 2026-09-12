# Credits — Three Colors Voice Pack

## Current audition path (MIDI / FluidSynth)

**Primary voice source for `audition_midi/`:** MuseScore General soundfont
rendered with FluidSynth (expressive MIDI trombone and violin).

### MuseScore General (HQ / Full SF3)

- File: `/usr/share/sounds/sf3/MuseScore_General_Full.sf3`
- Debian package: `musescore-general-soundfont` (0.2.1-1)
- Adaptation for MuseScore_General Copyright 2018-2021 S. Christian Collins
- License: MIT (component samples PD / CC0 as documented in the Debian
  package copyright). Includes Fluid (R3) GM heritage (Frank Wen et al., MIT).
- See: `/usr/share/doc/musescore-general-soundfont/copyright`

Programs used in the MIDI audition:

- Muted Trombone — GM #59 / program change 58
- Violin — GM #41 / program change 40

### Tools

- FluidSynth (`/usr/bin/fluidsynth`) — MIDI to WAV (reverb/chorus off)
- ffmpeg / sox — mono 16-bit normalize / stats
- Python mido — MIDI authoring (`build_midi_audition.py`)

## Earlier audition path (rejected for this gate)

University of Iowa Musical Instrument Samples (MIS) were used for the
grain-concat orchestral audition under `audition_orchestral/` and
`source_samples/`. Listener feedback: still too synthetic/effect-like.
Files retained for reference; not the source for `audition_midi/`.

Iowa MIS: https://theremin.music.uiowa.edu/ — attribution requested by
University of Iowa Electronic Music Studios.

Additive-synth takes under `audition/` are also reference-only.

## Build scripts

- `build_midi_audition.py` → `audition_midi/` (current)
- `build_orchestral_audition.py` → `audition_orchestral/` (prior Iowa grains)
