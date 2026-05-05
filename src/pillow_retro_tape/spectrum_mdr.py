"""Pillow plugin for ZX Spectrum Microdrive cartridge images (.mdr).

Microdrives were the small endless-loop tape "stringy floppies" sold for
the original 48K Spectrum (and the QL). MDR is a sector-by-sector dump
of one cartridge — see microdrive.py for the format.

Reconstructed Microdrive files become LoadEvents:
- type 3 (CODE) → KIND_CODE with the file's load address
- type 0 (BASIC) → KIND_BASIC, no address
- types 1/2 (number / character arrays) → KIND_RAW
"""

from typing import Iterator

from PIL import Image

from .loader import KIND_BASIC, KIND_CODE, KIND_RAW, LoadEvent
from .loader import extract_screens as _extract_screens_from_events
from .microdrive import (
    MIN_SECTORS,
    SECTOR_BYTES,
    TYPE_BASIC,
    TYPE_CODE,
    is_plausible_mdr,
    parse_mdr_files,
)
from .pillow_screen import ScreenSequenceImageFile


def iter_mdr_events(data: bytes) -> Iterator[LoadEvent]:
    for f in parse_mdr_files(data):
        if f.type == TYPE_CODE:
            yield LoadEvent(body=f.body, addr=f.start_addr, name=f.name, kind=KIND_CODE)
        elif f.type == TYPE_BASIC:
            yield LoadEvent(body=f.body, addr=None, name=f.name, kind=KIND_BASIC)
        else:
            yield LoadEvent(body=f.body, addr=None, name=f.name, kind=KIND_RAW)


def extract_screens(data: bytes) -> list[bytes]:
    return _extract_screens_from_events(iter_mdr_events(data))


def extract_screen(data: bytes) -> bytes:
    screens = extract_screens(data)
    if not screens:
        raise ValueError("no SCREEN$ found in MDR cartridge")
    return screens[0]


# --- Pillow plugin --------------------------------------------------------


class ZXMDRImageFile(ScreenSequenceImageFile):
    format = "ZXMDR"
    format_description = "ZX Spectrum Microdrive cartridge image"

    def _open(self):
        self.fp.seek(0, 2)
        size = self.fp.tell()
        self.fp.seek(0)
        if size < MIN_SECTORS * SECTOR_BYTES:
            raise SyntaxError(f"MDR file too short ({size} bytes)")
        data = self.fp.read()
        if not is_plausible_mdr(data):
            raise SyntaxError("not an MDR cartridge: no valid sectors found")
        try:
            screens = extract_screens(data)
        except ValueError as e:
            raise SyntaxError(f"failed to parse MDR: {e}") from e
        self._set_frames(screens)


def _accept(prefix: bytes) -> bool:
    # No magic bytes; rely on _open()'s plausibility check.
    return len(prefix) >= 16


def register() -> None:
    Image.register_open(ZXMDRImageFile.format, ZXMDRImageFile, _accept)
    Image.register_extension(ZXMDRImageFile.format, ".mdr")
