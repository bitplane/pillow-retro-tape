"""Pillow plugin for MGT (DISCiPLE / +D) disk images.

MGT was the disk format for the Miles Gordon Technology DISCiPLE and +D
disk interfaces — popular Spectrum add-ons in the late 80s. The same
file system is used by the SAM Coupé. See mgt.py for the spec.

Files of type 7 (ZX SCREEN$) and type 4 (ZX CODE) become LoadEvents
with their declared load address. SCREEN$ entries always load at $4000
length 6912.
"""

from collections.abc import Iterator

from PIL import Image

from .loader import KIND_BASIC, KIND_CODE, LoadEvent
from .loader import extract_screens as _extract_screens_from_events
from .mgt import (
    DIR_ENTRY_LEN,
    DS_SIZE,
    SS_SIZE,
    TYPE_BASIC,
    TYPE_CODE,
    TYPE_SCREEN,
    directory_looks_valid,
    parse_mgt_files,
)
from .pillow_screen import ScreenSequenceImageFile

# Standard sizes; some images in the wild are truncated, so we only use
# these for accept/_open sanity checking.
VALID_SIZES = {SS_SIZE, DS_SIZE}
MIN_MGT_SIZE = DIR_ENTRY_LEN * 80  # 20480 — at least the directory


def iter_mgt_events(data: bytes) -> Iterator[LoadEvent]:
    """Yield a LoadEvent per file in the MGT, in directory order.

    `MgtFile.body` already has the 9-byte +3DOS-style header stripped
    and is trimmed to the declared length (see mgt.py).
    """
    for f in parse_mgt_files(data):
        if f.type == TYPE_SCREEN:
            yield LoadEvent(body=f.body, addr=0x4000, name=f.name, kind=KIND_CODE)
        elif f.type == TYPE_CODE:
            yield LoadEvent(body=f.body, addr=f.start_addr, name=f.name, kind=KIND_CODE)
        elif f.type == TYPE_BASIC:
            yield LoadEvent(body=f.body, addr=None, name=f.name, kind=KIND_BASIC)
        # Snapshot types (5/9) and SAM types are skipped — those bodies
        # aren't loaded by a normal disk read.


def extract_screens(data: bytes) -> list[bytes]:
    return _extract_screens_from_events(iter_mgt_events(data))


def extract_screen(data: bytes) -> bytes:
    screens = extract_screens(data)
    if not screens:
        raise ValueError("no SCREEN$ found in MGT image")
    return screens[0]


# --- Pillow plugin --------------------------------------------------------


class ZXMGTImageFile(ScreenSequenceImageFile):
    format = "ZXMGT"
    format_description = "MGT (DISCiPLE / +D) disk image"

    def _open(self):
        self.fp.seek(0, 2)
        size = self.fp.tell()
        self.fp.seek(0)
        if size < MIN_MGT_SIZE:
            raise SyntaxError(f"MGT file too short ({size} bytes)")
        data = self.fp.read()
        if not directory_looks_valid(data):
            raise SyntaxError("not an MGT disk: directory doesn't look valid")
        try:
            screens = extract_screens(data)
        except ValueError as e:
            raise SyntaxError(f"failed to parse MGT: {e}") from e
        self._set_frames(screens)


def _accept(prefix: bytes) -> bool:
    # No magic bytes; rely on the directory-validity check in _open.
    return len(prefix) >= 16


def register() -> None:
    Image.register_open(ZXMGTImageFile.format, ZXMGTImageFile, _accept)
    Image.register_extension(ZXMGTImageFile.format, ".mgt")
