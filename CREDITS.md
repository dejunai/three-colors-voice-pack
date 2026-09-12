# Credits — Three Colors Voice Pack (Orchestral Audition)

## Primary sample source

**University of Iowa Musical Instrument Samples (MIS)**  
Electronic Music Studios, University of Iowa  
https://theremin.music.uiowa.edu/

Recordings used (downloaded 2026-09-12, stored under `source_samples/`):

### Tenor trombone (anechoic chamber, 16-bit / 44.1 kHz mono)
- `TenorTrombone.mf.C3B3.aiff`
- `TenorTrombone.mf.C4B4.aiff`
- `TenorTrombone.ff.C3B3.aiff`
- `TenorTrombone.pp.C3B3.aiff`
- `TenorTrombone.mf. E2B2.aiff`

### Violin, arco (anechoic chamber, 16-bit / 44.1 kHz mono)
- `Violin.arco.mf.sulG.G3B3.aiff`
- `Violin.arco.mf.sulG.B3B4.aiff`
- `Violin.arco.mf.sulD.D4A4.aiff`
- `Violin.arco.pp.sulG.B3Ab4.aiff`
- `Violin.arco.ff.sulG.G3B3.aiff`

These files were split into single-note grains and then time-scaled / lightly
pitch-slid into speech-like syllable phrases. Mute color on trombone is a
gentle resonant filter and open/muted blend applied **over** the real brass
samples (not a sine replacement).

### License / terms
The University of Iowa MIS collection is freely available for research,
education, and creative use as published by the University of Iowa Electronic
Music Studios. Attribution to the University of Iowa Electronic Music Studios
is requested. See https://theremin.music.uiowa.edu/ for current project notes.

## Secondary tools (installed on build machine; not sample sources)
- **ffmpeg** / **sox** / **rubberband-cli** — editing, spectrograms, time-stretch
- **MuseScore General Lite SF3** and **FluidR3_GM.sf2** — available on the system
  but **not** used as the voice source for this audition pack (real Iowa MIS
  samples were preferred)
- **Python**: numpy, scipy, soundfile

## Build script
`build_orchestral_audition.py` — regenerates the four audition WAVs in
`audition_orchestral/` from the grains under `source_samples/`.

## Audition outputs only
1. `audition_orchestral/trombone_bureaucratic_medium_v1.wav`
2. `audition_orchestral/trombone_dismissive_medium_v1.wav`
3. `audition_orchestral/violin_cautious_medium_v1.wav`
4. `audition_orchestral/violin_weary_medium_v1.wav`
