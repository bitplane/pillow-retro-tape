"""Microdrive cartridge image (.mdr) parsing.

A Microdrive cartridge holds a contiguous sequence of 543-byte sectors:

    bytes 0..14    sector header (15 bytes; byte 14 = checksum of bytes 0..13)
    bytes 15..29   record descriptor (15 bytes; byte 29 = checksum of bytes 15..28)
    bytes 30..541  data block (512 bytes)
    byte  542      data checksum

All checksums are `sum(bytes) % 255` (NOT % 256).

A classic Lunter / XZX / Spectator image is `254 sectors * 543 bytes
+ 1 trailing write-protect byte = 137923 bytes`. Warajevo accepts
images with anywhere from 10 to 254 sectors and ignores any trailing
bytes after the last whole sector.

Files are reconstructed by collecting all the records belonging to one
filename, sorting them by record number, and concatenating their data
blocks. The first record (RECNUM=0) for a normal `SAVE *` file starts
with a 9-byte file metadata header (the same shape as the Spectrum's
tape header):

    byte  0     file type   (0=BASIC, 1/2=DATA arrays, 3=CODE)
    bytes 1..2  file length (LE)
    bytes 3..4  start address / load address (LE)
    bytes 5..6  BASIC program-zone length
    bytes 7..8  BASIC autorun line

PRINT# files (record-flag bit 2 clear) are skipped — the corpus we
care about uses `SAVE *` exclusively.

References:
- World of Spectrum file-formats FAQ, MDR section
- Warajevo file format notes, MDR section
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterator

SECTOR_BYTES = 543
HEADER_LEN = 15  # sector header (bytes 0..14)
DESCRIPTOR_LEN = 15  # record descriptor (bytes 15..29)
DATA_OFFSET = HEADER_LEN + DESCRIPTOR_LEN  # 30
DATA_BYTES = 512  # bytes 30..541
DATA_CHECKSUM_OFFSET = SECTOR_BYTES - 1  # 542

MIN_SECTORS = 10
MAX_SECTORS = 254

INLINE_HEADER_LEN = 9  # +3DOS-style metadata at start of record 0

TYPE_BASIC = 0
TYPE_NUMBER_ARRAY = 1
TYPE_CHAR_ARRAY = 2
TYPE_CODE = 3


@dataclass(frozen=True)
class MicrodriveFile:
    name: str  # filename (10 chars, trailing spaces stripped)
    type: int  # 0=BASIC, 1/2=arrays, 3=CODE
    length: int  # declared body length (excluding the 9-byte metadata header)
    start_addr: int  # CODE: load address; BASIC: autostart line
    body: bytes  # the file payload (header stripped, trimmed to length)


def _checksum(data: bytes) -> int:
    """Microdrive sector / descriptor / data checksum: sum mod 255."""
    return sum(data) % 255


def _parse_record(sector: bytes) -> tuple[str, int, bytes] | None:
    """Decode one sector. Returns (filename, rec_num, data_block) for valid
    SAVE* data records, or None to skip (bad checksum, empty record, etc.).
    """
    if len(sector) < SECTOR_BYTES:
        return None
    if _checksum(sector[: HEADER_LEN - 1]) != sector[HEADER_LEN - 1]:
        return None
    if _checksum(sector[HEADER_LEN : DATA_OFFSET - 1]) != sector[DATA_OFFSET - 1]:
        return None
    if _checksum(sector[DATA_OFFSET:DATA_CHECKSUM_OFFSET]) != sector[DATA_CHECKSUM_OFFSET]:
        return None

    descriptor = sector[HEADER_LEN:DATA_OFFSET]
    rec_flag = descriptor[0]
    # Bit 0 set = "USED" / not a data record we want; skip.
    if rec_flag & 0x01:
        return None
    # Bit 2 clear = PRINT# data; we only handle SAVE* (bit 2 set).
    if not (rec_flag & 0x04):
        return None
    rec_num = descriptor[1]
    rec_len = descriptor[2] | (descriptor[3] << 8)
    if rec_len == 0 or rec_len > DATA_BYTES:
        return None
    name = descriptor[4:14].decode("ascii", errors="replace").rstrip()
    if not name:
        return None
    data = sector[DATA_OFFSET : DATA_OFFSET + rec_len]
    return name, rec_num, bytes(data)


def parse_mdr_files(data: bytes) -> Iterator[MicrodriveFile]:
    """Yield each file reconstructable from a Microdrive cartridge image."""
    n_sectors = len(data) // SECTOR_BYTES
    if n_sectors < MIN_SECTORS or n_sectors > MAX_SECTORS:
        return

    # Group records by filename
    records: dict[str, dict[int, bytes]] = defaultdict(dict)
    for i in range(n_sectors):
        sector = data[i * SECTOR_BYTES : (i + 1) * SECTOR_BYTES]
        parsed = _parse_record(sector)
        if parsed is None:
            continue
        name, rec_num, payload = parsed
        # First write of a given (name, rec_num) wins — extra copies are
        # the result of overwrites or rewrites, but for screen extraction
        # we want the original.
        records[name].setdefault(rec_num, payload)

    for name, rec_map in records.items():
        if 0 not in rec_map:
            continue  # no metadata header — skip
        ordered = b"".join(rec_map[k] for k in sorted(rec_map))
        if len(ordered) < INLINE_HEADER_LEN:
            continue
        header = ordered[:INLINE_HEADER_LEN]
        type_ = header[0]
        length = header[1] | (header[2] << 8)
        start_addr = header[3] | (header[4] << 8)
        body = ordered[INLINE_HEADER_LEN : INLINE_HEADER_LEN + length]
        if length and len(body) < length:
            continue  # missing later records — skip rather than emit truncated
        yield MicrodriveFile(
            name=name,
            type=type_,
            length=length,
            start_addr=start_addr,
            body=body,
        )


def is_plausible_mdr(data: bytes) -> bool:
    """Quick check: file length is in the valid sector-count range AND at
    least one sector parses cleanly."""
    n_sectors = len(data) // SECTOR_BYTES
    if n_sectors < MIN_SECTORS or n_sectors > MAX_SECTORS:
        return False
    for i in range(n_sectors):
        if _parse_record(data[i * SECTOR_BYTES : (i + 1) * SECTOR_BYTES]) is not None:
            return True
    return False
