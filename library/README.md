# library/ — placeholder instrumental-speech pack

144 wordless trombone/violin clips for *Three Colors of Madness*.

Rebuild from repo root: `python3 build_midi_library.py`

| Path | What |
|------|------|
| `*.wav` | deliverable clips (mono 44.1 kHz 16-bit PCM) |
| `midi/*.mid` | per-clip MIDI sources (edit one, `--only` that stem) |
| `manifest.json` | filename, style, length, take, duration, peak, render method |
| `validation_report.txt` | last validator run |

See the repo README for style list, duration bands, and programs.
