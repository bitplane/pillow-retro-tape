"""Pillow plugin for ZX Spectrum SCL files (TR-DOS packed disk).

SCL is a compact transfer format for TR-DOS disks: it stores only the
directory entries and concatenated file data, no empty sectors or disk
geometry. Magic bytes "SINCLAIR".

Loading-screen extraction: scan the directory for files of TR-DOS type 'C'
(CODE) with param2 == 6912 (the conventional SCREEN$ length).
"""

from PIL import Image

from .pillow_screen import ScreenSequenceImageFile
from .spectrum_screen import SCREEN_BYTES
from .tr_dos import TYPE_CODE, parse_scl_files

SCL_MAGIC = b"SINCLAIR"


SCREEN_LOAD_ADDR = 0x4000

_SCREEN_NAME_HINTS = ("SCR", "PIC", "TITL", "LOAD", "INTRO", "FRONT", "MAIN")


def _screen_priority(name: str, addr: int) -> int:
    upper = name.upper()
    if any(h in upper for h in _SCREEN_NAME_HINTS):
        return 0
    if addr == SCREEN_LOAD_ADDR:
        return 1
    return 2


def extract_screens(data: bytes) -> list[bytes]:
    """Return every plausible SCREEN$ in the SCL, ranked.

    Filename-hinted files (SCR/PIC/TITL/...) come first, then files
    loaded to $4000, then other 6912-byte CODE files.
    """
    candidates: list[tuple[int, int, bytes]] = []
    for order, f in enumerate(parse_scl_files(data)):
        if f.type == TYPE_CODE and f.param2 == SCREEN_BYTES and len(f.body) >= SCREEN_BYTES:
            pri = _screen_priority(f.name, f.param1)
            candidates.append((pri, order, f.body[:SCREEN_BYTES]))
    candidates.sort(key=lambda x: (x[0], x[1]))
    return [body for _, _, body in candidates]


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
