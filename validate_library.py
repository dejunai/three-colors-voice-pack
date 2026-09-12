#!/usr/bin/env python3
"""Validate library/: 144 expected WAVs, format, duration bands, no clip, unique takes."""
from build_midi_library import validate
import sys

if __name__ == "__main__":
    sys.exit(0 if validate() else 1)
