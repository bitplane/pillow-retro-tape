"""Pillow plugin for ZX Spectrum SLT files (Super Level Loader snapshot).

Layout:
    [v2 or v3 .z80 snapshot]
    [3 null bytes]
    "SLT"
    [8-byte table entries until type=0]:
        wType   (2 bytes LE)  -- 0=END, 1=LEVEL, 2=INSTRUCTIONS, 3=SCREEN,
                                 4=PICTURE, 5=POKE
        wId     (2 bytes LE)  -- type-dependent (level number for type 1
                                 and 3, etc.)
        dwSize  (4 bytes LE)  -- length in bytes of this entry's data
    [end-of-table marker (type=0 entry; id and size unused but present)]
    [data blocks, in table order, each compressed via the z80 RLE scheme]

Type 3 entries are 6912-byte SCREEN$ payloads (compressed). Type 1 entries
are level data (variable size). Frame 0 is the snapshot's main $4000 view;
subsequent frames are each type-3 entry in table order.

Reference: libspectrum z80.c -- enum slt_type.
"""

import struct
from collections.abc import Iterator

from PIL import Image

from .pillow_screen import ScreenSequenceImageFile
from .spectrum_screen import SCREEN_BYTES
from .spectrum_z80 import decompress_z80, parse_z80

SLT_SIGNATURE = b"\x00\x00\x00SLT"  # the 3 null bytes are part of the marker
SLT_TYPE_END = 0
SLT_TYPE_LEVEL = 1
SLT_TYPE_INSTRUCTIONS = 2
SLT_TYPE_SCREEN = 3
SLT_TYPE_PICTURE = 4
SLT_TYPE_POKE = 5

TABLE_ENTRY_LEN = 8


def _find_signature(data: bytes) -> int:
    """Locate the SLT signature (3 NULs + 'SLT'). Returns the offset of
    the first byte AFTER the signature, or -1 if not present."""
    pos = data.find(SLT_SIGNATURE)
    if pos < 0:
        return -1
    return pos + len(SLT_SIGNATURE)


def iter_slt_entries(data: bytes) -> Iterator[tuple[int, int, bytes]]:
    """Yield (type, id, data_block) tuples from an SLT file.

    The type=END marker is not yielded.
    """
    sig_end = _find_signature(data)
    if sig_end < 0:
        return  # no SLT extension; just a regular z80
    # Walk the table.
    table_start = sig_end
    entries: list[tuple[int, int, int]] = []  # (type, id, size)
    cursor = table_start
    while cursor + TABLE_ENTRY_LEN <= len(data):
        wtype, wid, dwsize = struct.unpack_from("<HHI", data, cursor)
        cursor += TABLE_ENTRY_LEN
        if wtype == SLT_TYPE_END:
            break
        entries.append((wtype, wid, dwsize))
    table_end = cursor
    # Data blocks follow the table in table order.
    block_start = table_end
    for wtype, wid, dwsize in entries:
        if block_start + dwsize > len(data):
            raise ValueError(f"SLT block (type={wtype} id={wid} size={dwsize}) runs past EOF")
        yield wtype, wid, bytes(data[block_start : block_start + dwsize])
        block_start += dwsize


def _z80_snapshot_bytes(data: bytes) -> bytes:
    """Slice off just the underlying z80 snapshot (everything before the
    SLT signature) so we can feed it to parse_z80."""
    sig_pos = data.find(SLT_SIGNATURE)
    return data if sig_pos < 0 else data[:sig_pos]


def iter_slt_events(data: bytes):
    """Yield events for the underlying snapshot plus any SLT-table screens."""
    from .loader import KIND_SNAPSHOT, LoadEvent

    try:
        snap = parse_z80(_z80_snapshot_bytes(data))
    except ValueError:
        snap = None

    if snap is not None:
        main = snap.screen()
        if any(main):
            yield LoadEvent(body=main, addr=0x4000, name="bank5", kind=KIND_SNAPSHOT)
        shadow = snap.shadow_screen()
        if shadow is not None and any(shadow):
            yield LoadEvent(body=shadow, addr=0x4000, name="shadow", kind=KIND_SNAPSHOT)

    # SLT type-3 entries are compressed-RLE 6912-byte screens.
    for wtype, wid, block in iter_slt_entries(data):
        if wtype != SLT_TYPE_SCREEN:
            continue
        try:
            screen, _ = decompress_z80(block, max_output=SCREEN_BYTES)
        except ValueError:
            continue
        if len(screen) < SCREEN_BYTES:
            continue
        yield LoadEvent(
            body=screen[:SCREEN_BYTES],
            addr=0x4000,
            name=f"slt-screen-{wid}",
            kind=KIND_SNAPSHOT,
        )


def extract_screens(data: bytes) -> list[bytes]:
    from .loader import extract_screens as _ext

    return _ext(iter_slt_events(data))


def extract_screen(data: bytes) -> bytes:
    screens = extract_screens(data)
    if not screens:
        raise ValueError("no SCREEN$ found in SLT file")
    return screens[0]


# --- Pillow plugin --------------------------------------------------------


class ZXSLTImageFile(ScreenSequenceImageFile):
    format = "ZXSLT"
    format_description = "ZX Spectrum SLT (Super Level Loader) snapshot"

    def _open(self):
        self.fp.seek(0, 2)
        size = self.fp.tell()
        self.fp.seek(0)
        if size < 30:
            raise SyntaxError("SLT file too short")
        data = self.fp.read()
        if SLT_SIGNATURE not in data:
            # No SLT marker present -> this is just a z80 with .slt extension.
            # Fall through to the z80 plugin by raising.
            raise SyntaxError("no SLT signature in file")
        try:
            screens = extract_screens(data)
        except ValueError as e:
            raise SyntaxError(f"failed to parse SLT: {e}") from e
        self._set_frames(screens)


def _accept(prefix: bytes) -> bool:
    return len(prefix) >= 16


def register() -> None:
    Image.register_open(ZXSLTImageFile.format, ZXSLTImageFile, _accept)
    Image.register_extension(ZXSLTImageFile.format, ".slt")
