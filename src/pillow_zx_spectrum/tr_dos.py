"""TR-DOS file system parsing (used by .scl and .trd disk images).

A TR-DOS disk has 16 sectors of 256 bytes per track. The directory occupies
the first 8 sectors (2048 bytes) of track 0 as up to 128 sixteen-byte
entries; sector 9 of track 0 holds the volume info (file count, free
sectors, disk type, label).

Directory entry (16 bytes):
    0..7    filename (ASCII, space-padded; 0x00 first byte = end-of-dir)
    8       extension/type byte ('B'=BASIC, 'C'=CODE, 'D'=number array,
                                 '#'=char array, ...)
    9..10   param1 (CODE: load address; BASIC: autostart line)
    11..12  param2 (CODE: length; BASIC: variable area offset)
    13      length in 256-byte sectors
    14      starting sector (1..16)
    15      starting track (0..159)

The SCL container reuses the entry layout but drops bytes 14-15 (start
sector / track), since SCL stores files concatenated in directory order
rather than at fixed disk positions.
"""

import struct
from dataclasses import dataclass
from typing import Iterator

SECTOR_BYTES = 256
SECTORS_PER_TRACK = 16
DIR_ENTRY_LEN = 16
SCL_DIR_ENTRY_LEN = 14  # SCL drops start_sector + start_track
MAX_DIR_ENTRIES = 128

TYPE_BASIC = ord("B")
TYPE_CODE = ord("C")  # SCREEN$ is type='C', length=6912, addr=$4000
TYPE_NUMBER_ARRAY = ord("D")
TYPE_CHAR_ARRAY = ord("#")


@dataclass(frozen=True)
class TrDosFile:
    name: str  # 8-char ASCII, trailing spaces stripped
    type: int  # the extension byte (e.g. ord('C') for CODE)
    param1: int  # CODE: load address; BASIC: autostart line
    param2: int  # CODE: length; BASIC: variable area offset
    sectors: int  # length in 256-byte sectors
    body: bytes  # the actual file bytes (sectors * 256)


def _parse_entry_metadata(entry: bytes) -> tuple[str, int, int, int, int] | None:
    """Parse the 9..13 region common to TRD and SCL directory entries.

    Returns (name, type, param1, param2, sectors) or None for end-of-dir.
    """
    if entry[0] == 0x00:
        return None  # end-of-directory marker
    name = entry[0:8].decode("ascii", errors="replace").rstrip()
    type_ = entry[8]
    param1, param2 = struct.unpack_from("<HH", entry, 9)
    sectors = entry[13]
    return name, type_, param1, param2, sectors


def parse_scl_files(data: bytes) -> Iterator[TrDosFile]:
    """Yield every file in an SCL container.

    SCL = "SINCLAIR" (8) + N (1) + N×14-byte entries + concatenated
    file bodies + 4-byte LE checksum.
    """
    if not data.startswith(b"SINCLAIR"):
        raise ValueError("not an SCL file")
    n_files = data[8]
    if n_files > MAX_DIR_ENTRIES:
        raise ValueError(f"SCL claims {n_files} files (>{MAX_DIR_ENTRIES})")

    entries_start = 9
    body_start = entries_start + n_files * SCL_DIR_ENTRY_LEN

    cursor = body_start
    for i in range(n_files):
        entry = data[entries_start + i * SCL_DIR_ENTRY_LEN : entries_start + (i + 1) * SCL_DIR_ENTRY_LEN]
        meta = _parse_entry_metadata(entry)
        if meta is None:
            # SCL spec uses N as the actual file count, but be defensive.
            continue
        name, type_, p1, p2, sectors = meta
        body_len = sectors * SECTOR_BYTES
        if cursor + body_len > len(data):
            # Truncated SCL — yield what we can of this file then stop.
            available = len(data) - cursor
            if available >= SECTOR_BYTES:
                yield TrDosFile(
                    name=name,
                    type=type_,
                    param1=p1,
                    param2=p2,
                    sectors=available // SECTOR_BYTES,
                    body=bytes(data[cursor : cursor + (available // SECTOR_BYTES) * SECTOR_BYTES]),
                )
            return
        yield TrDosFile(
            name=name,
            type=type_,
            param1=p1,
            param2=p2,
            sectors=sectors,
            body=bytes(data[cursor : cursor + body_len]),
        )
        cursor += body_len


def parse_trd_files(data: bytes) -> Iterator[TrDosFile]:
    """Yield every file in a TR-DOS raw disk image (.trd).

    Geometry: 16 sectors × 256 bytes per track. Sides interleaved as
    (track 0 side 0, track 0 side 1, track 1 side 0, ...). Directory
    occupies the first 8 sectors of track 0 side 0 as 128 × 16-byte
    entries; entry with name[0]=0 marks end-of-directory.
    """
    if len(data) < 0x900:
        raise ValueError("TRD file too short")

    # Detect geometry from the system sector if possible, otherwise infer
    # from total file size.
    sides = _detect_trd_sides(data)
    track_bytes = SECTORS_PER_TRACK * SECTOR_BYTES  # 4096

    for i in range(MAX_DIR_ENTRIES):
        entry = data[i * DIR_ENTRY_LEN : (i + 1) * DIR_ENTRY_LEN]
        meta = _parse_entry_metadata(entry)
        if meta is None:
            return
        name, type_, p1, p2, sectors = meta
        start_sector = entry[14]  # 0..15 (per Sinclair Wiki TRD spec)
        start_track = entry[15]  # logical track (counts both sides on DS)
        offset = _trd_offset(start_track, start_sector, sides, track_bytes)
        body_len = sectors * SECTOR_BYTES
        if offset >= len(data):
            # File starts past the end of the (truncated) image — skip.
            continue
        if offset + body_len > len(data):
            # Truncated TRD — yield what's actually in the file.
            body_len = (len(data) - offset) // SECTOR_BYTES * SECTOR_BYTES
            if body_len == 0:
                continue
        yield TrDosFile(
            name=name,
            type=type_,
            param1=p1,
            param2=p2,
            sectors=body_len // SECTOR_BYTES,
            body=bytes(data[offset : offset + body_len]),
        )


def _detect_trd_sides(data: bytes) -> int:
    """Detect single vs double-sided TRD from file size."""
    n = len(data)
    if n in (163840, 327680):
        return 2 if n == 327680 else 1  # 40-track ds vs ss; both 80-track ss
    if n == 655360:
        return 2  # 80-track ds
    # Fallback: assume double-sided 80 tracks (most common).
    return 2


def _trd_offset(track: int, sector: int, sides: int, track_bytes: int) -> int:
    """Convert logical (track, sector) to byte offset.

    TR-DOS interleaves sides: track 0 side 0, track 0 side 1, track 1
    side 0, ... So a logical "track" in the directory entry counts every
    physical track-side. For single-sided images we still use the same
    formula (sides=1 -> no interleaving).
    """
    return track * track_bytes + sector * SECTOR_BYTES


def make_trd_geometry_ok(data: bytes) -> bool:
    """Quick sanity check: does the file size match a known TRD geometry?"""
    return len(data) in (163840, 327680, 655360)


def make_dir_entry(
    name: str,
    type_: int,
    param1: int,
    param2: int,
    sectors: int,
    *,
    start_sector: int = 0,
    start_track: int = 0,
    include_position: bool = True,
) -> bytes:
    """Build a directory entry. With include_position=False emits the
    14-byte SCL flavour (no start_sector/start_track tail)."""
    name_bytes = name.encode("ascii")[:8].ljust(8, b" ")
    head = name_bytes + bytes([type_]) + struct.pack("<HH", param1 & 0xFFFF, param2 & 0xFFFF) + bytes([sectors])
    if include_position:
        return head + bytes([start_sector, start_track])
    return head
