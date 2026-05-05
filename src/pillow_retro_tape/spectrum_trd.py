"""Pillow plugin for ZX Spectrum TRD files (TR-DOS raw disk image).

A TRD is a flat sector-by-sector dump of a TR-DOS floppy. No magic bytes
or container header — geometry is inferred from the file size:
    163840 bytes  = 40 tracks single-sided
    327680 bytes  = 40 tracks double-sided OR 80 tracks single-sided
    655360 bytes  = 80 tracks double-sided

The file system layout is documented in tr_dos.py.
"""

from PIL import Image

from .pillow_screen import ScreenSequenceImageFile
from .spectrum_screen import SCREEN_BYTES
from .tr_dos import TYPE_CODE, parse_trd_files

TRD_VALID_SIZES = {163840, 327680, 655360}
MIN_TRD_SIZE = 0x900  # directory + system sector minimum


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
    """Return every plausible SCREEN$ in the TRD, ranked.

    Filename-hinted files (SCR/PIC/TITL/...) come first, then files
    loaded to $4000, then other 6912-byte CODE files.
    """
    candidates: list[tuple[int, int, bytes]] = []
    for order, f in enumerate(parse_trd_files(data)):
        if f.type == TYPE_CODE and f.param2 == SCREEN_BYTES and len(f.body) >= SCREEN_BYTES:
            pri = _screen_priority(f.name, f.param1)
            candidates.append((pri, order, f.body[:SCREEN_BYTES]))
    candidates.sort(key=lambda x: (x[0], x[1]))
    return [body for _, _, body in candidates]


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
    # No magic; file size check happens in _open. Keep accept loose for
    # extension-based dispatch.
    return len(prefix) >= 16


def register() -> None:
    Image.register_open(ZXTRDImageFile.format, ZXTRDImageFile, _accept)
    Image.register_extension(ZXTRDImageFile.format, ".trd")
