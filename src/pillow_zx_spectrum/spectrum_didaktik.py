"""Pillow plugin for ZX Spectrum Didaktik D40/D80 disk images.

Reads the MDOS file system (see didaktik.py for the format) and turns
each `B` (CODE) and `P` (BASIC) file into a LoadEvent. The `B` file's
`param1` is its load address; BASIC files have no address and their
body just feeds the BASIC-only-no-screen path.
"""

from collections.abc import Iterator

from PIL import Image

from .didaktik import (
    is_plausible_didaktik,
    parse_didaktik_files,
)
from .loader import KIND_BASIC, KIND_CODE, KIND_RAW, LoadEvent
from .loader import extract_screens as _extract_screens_from_events
from .pillow_screen import ScreenSequenceImageFile


def iter_didaktik_events(data: bytes) -> Iterator[LoadEvent]:
    for f in parse_didaktik_files(data):
        if f.type == "B":
            yield LoadEvent(body=f.body, addr=f.param1, name=f.name, kind=KIND_CODE)
        elif f.type == "P":
            yield LoadEvent(body=f.body, addr=None, name=f.name, kind=KIND_BASIC)
        else:
            yield LoadEvent(body=f.body, addr=None, name=f.name, kind=KIND_RAW)


def extract_screens(data: bytes) -> list[bytes]:
    return _extract_screens_from_events(iter_didaktik_events(data))


def extract_screen(data: bytes) -> bytes:
    screens = extract_screens(data)
    if not screens:
        raise ValueError("no SCREEN$ found in Didaktik image")
    return screens[0]


# --- Pillow plugin --------------------------------------------------------


class ZXDidaktikImageFile(ScreenSequenceImageFile):
    format = "ZXDIDAKTIK"
    format_description = "ZX Spectrum Didaktik D40/D80 disk image"

    def _open(self):
        self.fp.seek(0, 2)
        size = self.fp.tell()
        self.fp.seek(0)
        if size < 14 * 512:  # need at least boot + FAT + directory
            raise SyntaxError("Didaktik image too short")
        data = self.fp.read()
        if not is_plausible_didaktik(data):
            raise SyntaxError("not a Didaktik image: missing SDOS marker or directory")
        try:
            screens = extract_screens(data)
        except ValueError as e:
            raise SyntaxError(f"failed to parse Didaktik image: {e}") from e
        self._set_frames(screens)


def _accept(prefix: bytes) -> bool:
    # Pillow only passes 16 bytes; the SDOS marker lives at offset 204.
    # Real validation happens in _open.
    return len(prefix) >= 16


def register() -> None:
    Image.register_open(ZXDidaktikImageFile.format, ZXDidaktikImageFile, _accept)
    Image.register_extension(ZXDidaktikImageFile.format, ".d40")
    Image.register_extension(ZXDidaktikImageFile.format, ".d80")
