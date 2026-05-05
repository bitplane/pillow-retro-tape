"""Pillow plugin for ZX Spectrum TRD files (TR-DOS raw disk image).

A TRD is a flat sector-by-sector dump of a TR-DOS floppy. No magic bytes
or container header — geometry is inferred from the file size:
    163840 bytes  = 40 tracks single-sided
    327680 bytes  = 40 tracks double-sided OR 80 tracks single-sided
    655360 bytes  = 80 tracks double-sided

The file system layout is documented in tr_dos.py.
"""

from typing import Iterator

from PIL import Image

from .loader import KIND_BASIC, KIND_CODE, LoadEvent
from .loader import extract_screens as _extract_screens_from_events
from .pillow_screen import ScreenSequenceImageFile
from .tr_dos import TYPE_CODE, parse_trd_files

TRD_VALID_SIZES = {163840, 327680, 655360}
MIN_TRD_SIZE = 0x900  # directory + system sector minimum


def iter_trd_events(data: bytes) -> Iterator[LoadEvent]:
    """Yield a LoadEvent per file in the TRD, in directory order."""
    for f in parse_trd_files(data):
        kind = KIND_CODE if f.type == TYPE_CODE else KIND_BASIC
        addr = f.param1 if f.type == TYPE_CODE else None
        yield LoadEvent(body=f.body, addr=addr, name=f.name, kind=kind)


def extract_screens(data: bytes) -> list[bytes]:
    return _extract_screens_from_events(iter_trd_events(data))


def extract_screen(data: bytes) -> bytes:
    screens = extract_screens(data)
    if not screens:
        raise ValueError("no SCREEN$ file found in TRD image")
    return screens[0]


# --- Pillow plugin --------------------------------------------------------


class ZXTRDImageFile(ScreenSequenceImageFile):
    format = "ZXTRD"
    format_description = "ZX Spectrum TRD (TR-DOS raw) disk image"

    def _open(self):
        self.fp.seek(0, 2)
        size = self.fp.tell()
        self.fp.seek(0)
        if size < MIN_TRD_SIZE:
            raise SyntaxError(f"TRD file too short ({size} bytes)")
        data = self.fp.read()
        # Sanity-check the system sector's TR-DOS magic byte (0x10 at
        # offset 0x8E7). Avoids claiming arbitrary 16K+ binaries.
        if len(data) >= 0x8E8 and data[0x8E7] != 0x10:
            raise SyntaxError("missing TR-DOS magic 0x10 in system sector")
        try:
            screens = extract_screens(data)
        except ValueError as e:
            raise SyntaxError(f"failed to parse TRD: {e}") from e
        self._set_frames(screens)


def _accept(prefix: bytes) -> bool:
    return len(prefix) >= 16


def register() -> None:
    Image.register_open(ZXTRDImageFile.format, ZXTRDImageFile, _accept)
    Image.register_extension(ZXTRDImageFile.format, ".trd")
