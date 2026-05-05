"""Pillow plugin for ZX Spectrum SCL files (TR-DOS packed disk).

SCL is a compact transfer format for TR-DOS disks: it stores only the
directory entries and concatenated file data, no empty sectors or disk
geometry. Magic bytes "SINCLAIR".
"""

from typing import Iterator

from PIL import Image

from .loader import KIND_BASIC, KIND_CODE, LoadEvent
from .loader import extract_screens as _extract_screens_from_events
from .pillow_screen import ScreenSequenceImageFile
from .tr_dos import TYPE_CODE, parse_scl_files

SCL_MAGIC = b"SINCLAIR"


def iter_scl_events(data: bytes) -> Iterator[LoadEvent]:
    """Yield a LoadEvent per file in the SCL, in directory order."""
    for f in parse_scl_files(data):
        kind = KIND_CODE if f.type == TYPE_CODE else KIND_BASIC
        addr = f.param1 if f.type == TYPE_CODE else None
        yield LoadEvent(body=f.body, addr=addr, name=f.name, kind=kind)


def extract_screens(data: bytes) -> list[bytes]:
    return _extract_screens_from_events(iter_scl_events(data))


def extract_screen(data: bytes) -> bytes:
    screens = extract_screens(data)
    if not screens:
        raise ValueError("no SCREEN$ file found in SCL image")
    return screens[0]


# --- Pillow plugin --------------------------------------------------------


class ZXSCLImageFile(ScreenSequenceImageFile):
    format = "ZXSCL"
    format_description = "ZX Spectrum SCL (TR-DOS packed) disk image"

    def _open(self):
        head = self.fp.read(len(SCL_MAGIC))
        self.fp.seek(0)
        if head != SCL_MAGIC:
            raise SyntaxError("not an SCL file")
        data = self.fp.read()
        try:
            screens = extract_screens(data)
        except ValueError as e:
            raise SyntaxError(f"failed to parse SCL: {e}") from e
        self._set_frames(screens)


def _accept(prefix: bytes) -> bool:
    return prefix.startswith(SCL_MAGIC)


def register() -> None:
    Image.register_open(ZXSCLImageFile.format, ZXSCLImageFile, _accept)
    Image.register_extension(ZXSCLImageFile.format, ".scl")
