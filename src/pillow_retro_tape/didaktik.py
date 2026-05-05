"""Didaktik D40/D80 (MDOS) disk image parsing.

Didaktik D40 and D80 were Czechoslovak floppy disk add-ons for the ZX
Spectrum, using the MDOS file system on raw double-sided 9- or
10-sectors-per-track disks (.d40 / .d80).

Layout
======

    Sector 0       Boot sector (geometry + "SDOS" marker at byte 204)
    Sectors 1..5   12-bit FAT (one entry per logical sector)
    Sector  6      Start of directory (8 sectors = 128 32-byte entries)
    Sector  14+    Data area

(Note: the Cygnus MDOS spec describes the directory as occupying
"sectors 7-14", but every D80 image we've inspected has its directory
starting at logical sector 6 — the spec appears to use 1-indexed
sector numbering. We use 0-indexed throughout.)

Boot sector fields
==================

    byte 177      flags (bit 3 = 40T double-stepping, bit 4 = double-sided)
    byte 178      tracks per side
    byte 179      sectors per track
    bytes 192..201 disk label
    bytes 204..207 b"SDOS"

Directory entry (32 bytes)
==========================

    byte  0       file type (one of "PBNCSQ"; 0xE5 = deleted)
    bytes 1..10   filename, NUL-padded
    bytes 11..12  body length low 16 bits (LE)
    bytes 13..14  CODE: load address; BASIC: autostart line
    bytes 15..16  BASIC program length without variables (unused for CODE)
    bytes 17..18  first sector / FAT entry (LE)
    byte  19      always 0
    byte  20      attributes (HSPARWED bit order)
    byte  21      third length byte for files > 65535
    bytes 22..31  0xE5 padding

FAT12
=====

    Two 12-bit entries are packed into 3 bytes (low/high nibble split).
    Special values:
        0       free
        0xC00   empty file
        0xDDD   reserved
        0xDFF   bad sector
        0xE00.. end-of-file marker; tail = 0xE00 + (length % 512)

Reading: start at the directory entry's first_sector; append sector
data; follow the FAT; stop when the next value is >= 0xE00. Skip files
with broken chains (cycles, out-of-range links, hits on reserved/bad).
"""

from collections import OrderedDict
from dataclasses import dataclass
from typing import Iterator

SECTOR_BYTES = 512
BOOT_SECTOR = 0
FAT_SECTORS = (1, 6)  # half-open: [1, 6) — sectors 1..5
DIR_SECTORS = (6, 14)  # half-open: [6, 14) — sectors 6..13
DATA_SECTOR_START = 14
DIR_ENTRY_LEN = 32
SDOS_MARKER = b"SDOS"
SDOS_MARKER_OFFSET = 204
DELETED_MARKER = 0xE5
PADDING = 0xE5

# FAT12 special values (Cygnus naming)
FAT_FREE = 0x000
FAT_EMPTY_FILE = 0xC00
FAT_RESERVED = 0xDDD
FAT_BAD_SECTOR = 0xDFF
FAT_EOF_BASE = 0xE00  # 0xE00 + (length % 512) marks end


@dataclass(frozen=True)
class DidaktikGeometry:
    tracks: int
    sides: int
    sectors_per_track: int
    sector_bytes: int = SECTOR_BYTES

    @property
    def total_sectors(self) -> int:
        return self.tracks * self.sides * self.sectors_per_track

    @property
    def total_bytes(self) -> int:
        return self.total_sectors * self.sector_bytes


@dataclass(frozen=True)
class DidaktikFile:
    type: str  # "P", "B", "N", "C", "S", "Q"
    name: str  # filename, trailing NUL/space stripped
    length: int  # declared body length
    param1: int  # CODE: load address; BASIC: autostart line
    param2: int  # BASIC: program length; CODE: unused
    attrs: int  # attribute byte (HSPARWED)
    body: bytes  # reconstructed file body (trimmed to length)


# --- FAT12 helpers ----------------------------------------------------------


def fat12_get(fat: bytes, index: int) -> int:
    """Read 12-bit FAT entry at `index`.

    MDOS uses a non-standard FAT12 packing within each 3-byte pair:

        byte 0: entry A low 8 bits
        byte 1: entry A high 4 bits (high nibble) + entry B high 4 bits (low nibble)
        byte 2: entry B low 8 bits

    (Standard Microsoft FAT12 swaps the two nibbles of byte 1 — that
    layout decodes MDOS chains incorrectly.)
    """
    pair = index // 2
    off = pair * 3
    if off + 2 >= len(fat):
        return 0
    b1 = fat[off + 1]
    if index & 1:
        return fat[off + 2] | ((b1 & 0x0F) << 8)
    return fat[off] | (((b1 >> 4) & 0x0F) << 8)


# --- Boot sector ------------------------------------------------------------


def parse_geometry(data: bytes) -> DidaktikGeometry:
    """Read the boot sector and return geometry. Raises ValueError if
    the SDOS marker is absent or geometry is implausible."""
    if len(data) < SECTOR_BYTES:
        raise ValueError("Didaktik image too short for a boot sector")
    if data[SDOS_MARKER_OFFSET : SDOS_MARKER_OFFSET + 4] != SDOS_MARKER:
        raise ValueError("missing SDOS marker in boot sector")
    flags = data[177]
    tracks = data[178]
    sectors_per_track = data[179]
    sides = 2 if flags & 0x10 else 1
    if not (1 <= tracks <= 100) or not (8 <= sectors_per_track <= 16):
        raise ValueError(f"implausible Didaktik geometry: tracks={tracks} spt={sectors_per_track}")
    return DidaktikGeometry(tracks=tracks, sides=sides, sectors_per_track=sectors_per_track)


# --- Directory --------------------------------------------------------------


_VALID_TYPES = set("PBNCSQ")


def _parse_directory_entry(entry: bytes) -> tuple[str, str, int, int, int, int, int] | None:
    """Decode one 32-byte directory entry, or None for empty/invalid."""
    if len(entry) < DIR_ENTRY_LEN:
        return None
    type_byte = entry[0]
    if type_byte == 0 or type_byte == DELETED_MARKER:
        return None
    type_char = chr(type_byte) if 32 <= type_byte < 127 else "?"
    if type_char not in _VALID_TYPES:
        return None
    name_bytes = entry[1:11]
    # Filename ends at first NUL byte; strip trailing spaces too.
    nul_pos = name_bytes.find(b"\x00")
    if nul_pos >= 0:
        name_bytes = name_bytes[:nul_pos]
    try:
        name = name_bytes.decode("ascii", errors="replace").rstrip()
    except ValueError:
        return None
    length = entry[11] | (entry[12] << 8) | (entry[21] << 16)
    param1 = entry[13] | (entry[14] << 8)
    param2 = entry[15] | (entry[16] << 8)
    first_sector = entry[17] | (entry[18] << 8)
    attrs = entry[20]
    return type_char, name, length, param1, param2, first_sector, attrs


def _iter_directory_entries(data: bytes) -> Iterator[tuple]:
    dir_start = DIR_SECTORS[0] * SECTOR_BYTES
    dir_end = DIR_SECTORS[1] * SECTOR_BYTES
    if dir_end > len(data):
        return
    for off in range(dir_start, dir_end, DIR_ENTRY_LEN):
        parsed = _parse_directory_entry(data[off : off + DIR_ENTRY_LEN])
        if parsed is not None:
            yield parsed


# --- File reconstruction ----------------------------------------------------


def _read_file_body(
    data: bytes,
    fat: bytes,
    first_sector: int,
    declared_length: int,
    geometry: DidaktikGeometry,
) -> bytes | None:
    """Walk the FAT chain starting at `first_sector` and return the
    concatenated sector data trimmed to `declared_length`.

    Each entry < 0xC00 is a link to the next sector. Values >= 0xC00
    terminate the chain; the low 9 bits of the marker give the number
    of bytes used in the final sector (Cygnus's "EOF base" formulation
    actually masks to a tail in the bottom 9 bits — confirmed against
    real images by reproducing the directory length).
    """
    if first_sector == 0:
        return b""  # empty file
    total_sectors = geometry.total_sectors
    body = bytearray()
    seen: set[int] = set()
    sec = first_sector
    final_tail: int | None = None
    while True:
        if sec < DATA_SECTOR_START or sec >= total_sectors:
            return None
        if sec in seen:
            return None
        seen.add(sec)
        offset = sec * SECTOR_BYTES
        if offset + SECTOR_BYTES > len(data):
            return None
        body.extend(data[offset : offset + SECTOR_BYTES])
        nxt = fat12_get(fat, sec)
        if nxt >= 0xC00:
            # End-of-file marker; low 9 bits = bytes valid in the final
            # sector. tail==0 means the final sector is full.
            final_tail = nxt & 0x1FF
            break
        sec = nxt

    if final_tail is not None and final_tail and final_tail < SECTOR_BYTES:
        body = body[: -SECTOR_BYTES + final_tail]

    if declared_length and len(body) > declared_length:
        body = body[:declared_length]
    return bytes(body)


def parse_didaktik_files(data: bytes) -> Iterator[DidaktikFile]:
    """Yield each reconstructable file in the disk image."""
    try:
        geometry = parse_geometry(data)
    except ValueError:
        return
    fat_start = FAT_SECTORS[0] * SECTOR_BYTES
    fat_end = FAT_SECTORS[1] * SECTOR_BYTES
    if fat_end > len(data):
        return
    fat = data[fat_start:fat_end]

    # Group entries by name to dedupe (some disks have stale duplicates).
    seen_names: OrderedDict[str, None] = OrderedDict()
    for type_char, name, length, p1, p2, first_sector, attrs in _iter_directory_entries(data):
        if name in seen_names:
            continue
        body = _read_file_body(data, fat, first_sector, length, geometry)
        if body is None:
            continue
        seen_names[name] = None
        yield DidaktikFile(
            type=type_char,
            name=name,
            length=length,
            param1=p1,
            param2=p2,
            attrs=attrs,
            body=body,
        )


def is_plausible_didaktik(data: bytes) -> bool:
    """Cheap fingerprint: SDOS marker + at least one valid directory entry."""
    if len(data) < DIR_SECTORS[1] * SECTOR_BYTES:
        return False
    if data[SDOS_MARKER_OFFSET : SDOS_MARKER_OFFSET + 4] != SDOS_MARKER:
        return False
    return next(_iter_directory_entries(data), None) is not None
