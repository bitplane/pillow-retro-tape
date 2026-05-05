"""Pillow plugin for ZX Spectrum TAP tape files.

A TAP file is a flat sequence of records:

    [2-byte little-endian length][length bytes of standard ROM block]

Each standard ROM block is `flag + payload + checksum`. Header/data block
pairs are translated to `LoadEvent`s and fed into the unified screen
extractor (see loader.py).
"""

import struct
from typing import Iterator

from PIL import Image

from .blocks import DATA_FLAG, HEADER_FLAG, MIN_BLOCK_LEN, Block, Header, parse_block
from .loader import KIND_BASIC, KIND_CODE, LoadEvent
from .loader import extract_screens as _extract_screens_from_events
from .pillow_screen import ScreenSequenceImageFile


def iter_tap_blocks(data: bytes) -> Iterator[Block]:
    """Yield each standard ROM-loader Block in a TAP file."""
    i = 0
    while i < len(data):
        if i + 2 > len(data):
            raise ValueError(f"truncated TAP at offset {i}: missing length word")
        length = struct.unpack_from("<H", data, i)[0]
        i += 2
        if length < MIN_BLOCK_LEN:
            raise ValueError(f"TAP block too short at offset {i - 2}: {length} bytes")
        if i + length > len(data):
            raise ValueError(f"truncated TAP at offset {i}: block runs past EOF")
        yield parse_block(data[i : i + length])
        i += length


def iter_tap_events(tap_data: bytes) -> Iterator[LoadEvent]:
    """Yield a LoadEvent per `header + data` pair in the TAP."""
    pending: Header | None = None
    for block in iter_tap_blocks(tap_data):
        if block.is_header():
            pending = Header.from_block(block)
            continue
        if block.is_data() and pending is not None:
            kind = KIND_CODE if pending.type == 3 else KIND_BASIC
            yield LoadEvent(
                body=block.payload[: pending.length],
                addr=pending.param1 if pending.type == 3 else None,
                name=pending.name,
                kind=kind,
            )
        pending = None


def extract_screens(tap_data: bytes) -> list[bytes]:
    return _extract_screens_from_events(iter_tap_events(tap_data))


def extract_screen(tap_data: bytes) -> bytes:
    """Return the first SCREEN$ candidate (preserved for single-frame use)."""
    screens = extract_screens(tap_data)
    if not screens:
        raise ValueError("no screen found in TAP")
    return screens[0]


# --- Pillow plugin --------------------------------------------------------


class ZXTAPImageFile(ScreenSequenceImageFile):
    format = "ZXTAP"
    format_description = "ZX Spectrum TAP tape"

    def _open(self):
        self.fp.seek(0, 2)
        size = self.fp.tell()
        self.fp.seek(0)
        data = self.fp.read()
        if size != len(data):
            raise SyntaxError("could not read full TAP file")
        try:
            screens = extract_screens(data)
        except ValueError as e:
            raise SyntaxError(f"not a valid TAP file: {e}") from e
        self._set_frames(screens)


def _accept(prefix: bytes) -> bool:
    """Lightweight TAP fingerprint (full validation happens in _open).

    A real TAP starts with a 2-byte length followed by a flag byte that's
    either 0x00 (header) or 0xFF (data). Length must fit a non-empty block.
    """
    if len(prefix) < 3:
        return False
    length = prefix[0] | (prefix[1] << 8)
    return length >= MIN_BLOCK_LEN and prefix[2] in (HEADER_FLAG, DATA_FLAG)


def register() -> None:
    Image.register_open(ZXTAPImageFile.format, ZXTAPImageFile, _accept)
    Image.register_extension(ZXTAPImageFile.format, ".tap")
