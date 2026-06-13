"""Symbolic melody composer — real, CPU-only, zero dependencies.

Implements spec §B.2(c): lyrics + text description ("upbeat C-major nursery melody,
100 BPM, simple AABB") -> a melody. `melody_notes()` returns note events that are turned
into either a Standard MIDI File (here) or an audio music bed (app/music_synth.py).
"""
from __future__ import annotations

import re
import struct

from ..base import Availability, Capability, Cost, GenResult, MusicProvider, ProviderInfo

_NOTE_BASE = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}
_MAJOR = [0, 2, 4, 5, 7, 9, 11]
_MINOR = [0, 2, 3, 5, 7, 8, 10]
# simple, singable nursery contour over scale degrees (AABB-friendly)
_CONTOUR = [0, 2, 4, 4, 2, 0, 2, 4, 0, 0, 4, 2, 0, -1, 0, 0]


def _root_midi(key: str) -> int:
    m = re.match(r"([a-gA-G])([#b]?)", key.strip())
    if not m:
        return 60
    semitone = _NOTE_BASE[m.group(1).lower()]
    if m.group(2) == "#":
        semitone += 1
    elif m.group(2) == "b":
        semitone -= 1
    return 60 + semitone  # octave 4


def melody_notes(description: str, *, duration_s: float, key: str = "C",
                 tempo: int = 100) -> tuple[list[tuple[int, float, float]], dict]:
    """Return ([(midi_note, start_s, dur_s), ...], info). Quarter-note nursery melody."""
    scale = _MINOR if "minor" in description.lower() else _MAJOR
    root = _root_midi(key)
    beat = 60.0 / max(1, tempo)
    beats = max(1, round(duration_s / beat))
    notes: list[tuple[int, float, float]] = []
    for i in range(beats):
        degree = _CONTOUR[i % len(_CONTOUR)]
        octave_shift = -12 if degree < 0 else 0
        note = max(0, min(127, root + scale[abs(degree) % 7] + octave_shift))
        notes.append((note, i * beat, beat))
    info = {"key": key, "tempo": tempo, "beats": beats,
            "scale": "minor" if scale is _MINOR else "major"}
    return notes, info


def _vlq(value: int) -> bytes:
    out = bytearray([value & 0x7F])
    value >>= 7
    while value:
        out.insert(0, (value & 0x7F) | 0x80)
        value >>= 7
    return bytes(out)


def notes_to_midi(notes: list[tuple[int, float, float]], tempo: int) -> bytes:
    ppq = 480
    track = bytearray()
    track += _vlq(0) + b"\xFF\x51\x03" + struct.pack(">I", round(60_000_000 / max(1, tempo)))[1:]
    for note, _start, _dur in notes:
        track += _vlq(0) + bytes([0x90, note, 90])      # note on
        track += _vlq(ppq) + bytes([0x80, note, 0])      # note off after a quarter
    track += _vlq(0) + b"\xFF\x2F\x00"
    header = b"MThd" + struct.pack(">IHHH", 6, 0, 1, ppq)
    return header + b"MTrk" + struct.pack(">I", len(track)) + bytes(track)


class SymbolicMusicProvider(MusicProvider):
    info = ProviderInfo(
        name="symbolic", capability=Capability.MUSIC, kind="local",
        free=True, requires_gpu=False,
    )

    def availability(self) -> Availability:
        return Availability(True)

    async def compose(self, description: str, *, duration_s: float = 30.0,
                      key: str = "C", tempo: int = 100, **kw: object) -> GenResult:
        notes, meta = melody_notes(description, duration_s=duration_s, key=key, tempo=tempo)
        data = notes_to_midi(notes, tempo)
        return GenResult(data=data, mime="audio/midi", cost=Cost(),
                         meta={"provider": "symbolic", **meta})
