"""Parsing of +3DOS file headers (Spectrum +3 disk file format).

Every file written to a +3 disk by 48-BASIC's `SAVE` command is preceded
by a 128-byte +3DOS header that mirrors the tape header conceptually:

    offset  size  field
    0..7    8     "PLUS3DOS"
    8       1     0x1A  (CP/M EOF)
    9       1     issue number (1)
    10      1     version number (0)
    11..14  4     total file length (header + body), little-endian uint32
    15      1     type    (0=PROGRAM, 1=NumArr, 2=CharArr, 3=CODE/SCREEN$)
    16..17  2     length  (body length)
    18..19  2     param1  (CODE: load address; PROGRAM: autostart line)
    20..21  2     param2
    22..126 ...   reserved (zero)
    127     1     checksum (sum of bytes 0..126 mod 256)

Headers are written at the start of a 512-byte disk sector, so the magic
appears on a 512-byte boundary in a logical-sector byte stream.
"""

import struct
from collections.abc import Iterator
from dataclasses import dataclass

PLUS3DOS_MAGIC = b"PLUS3DOS\x1a"
HEADER_LEN = 128
SECTOR_ALIGN = 512

TYPE_PROGRAM = 0
TYPE_NUMBER_ARRAY = 1
TYPE_CHAR_ARRAY = 2
TYPE_CODE = 3


@dataclass(frozen=True)
class Plus3File:
    type: int
    length: int  # body length (excluding the 128-byte header)
    param1: int
    param2: int
    body: bytes
    offset: int  # offset of the +3DOS header in the source bytes


def _checksum_ok(header: bytes) -> bool:
    return (sum(header[:127]) & 0xFF) == header[127]


def parse_at(data: bytes, offset: int, *, verify_checksum: bool = True) -> Plus3File | None:
    """Try to parse a +3DOS file header at `offset`.

    Returns None if the magic doesn't match, the declared length runs past
    the buffer, or (when enabled) the header checksum is wrong.
    """
    if offset < 0 or offset + HEADER_LEN > len(data):
        return None
    if data[offset : offset + len(PLUS3DOS_MAGIC)] != PLUS3DOS_MAGIC:
        return None
    h = data[offset : offset + HEADER_LEN]
    if verify_checksum and not _checksum_ok(h):
        return None
    total = struct.unpack_from("<I", h, 11)[0]
    if total < HEADER_LEN or offset + total > len(data):
        return None
    return Plus3File(
        type=h[15],
        length=struct.unpack_from("<H", h, 16)[0],
        param1=struct.unpack_from("<H", h, 18)[0],
        param2=struct.unpack_from("<H", h, 20)[0],
        body=bytes(data[offset + HEADER_LEN : offset + total]),
        offset=offset,
    )


def find_plus3_files(
    data: bytes,
    *,
    align: int = SECTOR_ALIGN,
    verify_checksum: bool = True,
) -> Iterator[Plus3File]:
    """Yield every valid +3DOS file in `data`.

    By default we only consider `align`-aligned offsets (sector boundaries);
    pass `align=1` to scan every byte position.
    """
    for offset in range(0, len(data) - HEADER_LEN + 1, max(1, align)):
        if data[offset : offset + len(PLUS3DOS_MAGIC)] == PLUS3DOS_MAGIC:
            f = parse_at(data, offset, verify_checksum=verify_checksum)
            if f is not None:
                yield f


def make_plus3_header(
    type_: int,
    length: int,
    param1: int,
    param2: int = 0,
) -> bytes:
    """Build a 128-byte +3DOS header for a file with body of `length` bytes."""
    h = bytearray(HEADER_LEN)
    h[0:9] = PLUS3DOS_MAGIC
    h[9] = 1  # issue
    h[10] = 0  # version
    struct.pack_into("<I", h, 11, HEADER_LEN + length)
    h[15] = type_
    struct.pack_into("<H", h, 16, length & 0xFFFF)
    struct.pack_into("<H", h, 18, param1 & 0xFFFF)
    struct.pack_into("<H", h, 20, param2 & 0xFFFF)
    h[127] = sum(h[:127]) & 0xFF
    return bytes(h)
