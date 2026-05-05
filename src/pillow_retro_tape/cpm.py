"""CP/M file system reader for ZX Spectrum +3 / Amstrad PCW disks.

Disk layout (typical +3 single-sided 180K):
    Reserved tracks: 1 (track 0, 9 sectors x 512 bytes = 4608 bytes)
    Data area:       starts at track 1
    Allocation block size: 1024 bytes (2 sectors)
    Directory: 64 entries x 32 bytes = 2048 bytes (occupies blocks 0+1)

Directory entry (32 bytes):
    0       user (0..15) or 0xE5 if deleted
    1..8    filename (high bit of each byte may be a CP/M attribute flag)
    9..11   extension
    12      extent low byte
    13      reserved (S1)
    14      extent high byte (the "module" byte)
    15      record count (0..128, where each record is 128 bytes)
    16..31  16 allocation block numbers (1 byte each on disks <= 255 blocks)

Files larger than 16 KB span multiple directory entries (extents). To read
a file: gather all entries with matching (user, name, ext), sort by extent
number, concatenate the block lists, and read each block from the data
area. The last extent's record_count tells you how many trailing 128-byte
records to keep from the final block.

Reference: CP/M 2.2 spec; Amstrad +3 / PCW DPB.
"""

from dataclasses import dataclass

DELETED = 0xE5
DIR_ENTRY_LEN = 32
N_DIR_ENTRIES = 64  # +3 standard
RESERVED_TRACK_BYTES = 4608  # 1 track of 9*512
ALLOC_BLOCK_BYTES = 1024
RECORD_BYTES = 128
EXTENT_RECORDS = 128  # records per extent (= 16384 bytes)


@dataclass(frozen=True)
class CpmFile:
    user: int
    name: str  # 8-char ASCII, trailing spaces stripped
    ext: str  # 3-char ASCII, trailing spaces stripped
    body: bytes  # full reconstructed file body


def _decode_name(raw: bytes) -> str:
    """Decode a CP/M filename component, ignoring the high attribute bit."""
    return bytes(b & 0x7F for b in raw).decode("ascii", errors="replace").rstrip()


def list_files(
    flat: bytes,
    *,
    reserved_bytes: int = RESERVED_TRACK_BYTES,
    block_bytes: int = ALLOC_BLOCK_BYTES,
    n_dir_entries: int = N_DIR_ENTRIES,
) -> list[CpmFile]:
    """Reconstruct every regular CP/M file from a flat sector image.

    `flat` is the disk in logical-sector order (track 0, side 0, sector 1,
    sector 2, ...). The directory is the first 2048 bytes of the data
    area (i.e. starts at `reserved_bytes`).
    """
    dir_offset = reserved_bytes
    if len(flat) < dir_offset + DIR_ENTRY_LEN * n_dir_entries:
        return []

    # Group entries by (user, name, ext); each is a dict of extent -> entry.
    extents: dict[tuple[int, str, str], dict[int, tuple[list[int], int]]] = {}
    for i in range(n_dir_entries):
        e = flat[dir_offset + i * DIR_ENTRY_LEN : dir_offset + (i + 1) * DIR_ENTRY_LEN]
        if e[0] == DELETED or all(b == 0 for b in e):
            continue
        user = e[0]
        if user > 15:
            # Disk label / time stamps / random non-file entry.
            continue
        name = _decode_name(e[1:9])
        ext = _decode_name(e[9:12])
        extent = (e[12] & 0x1F) | ((e[14] & 0x3F) << 5)
        record_count = e[15]
        blocks = [b for b in e[16:32] if b]
        extents.setdefault((user, name, ext), {})[extent] = (blocks, record_count)

    files: list[CpmFile] = []
    for (user, name, ext), ext_map in extents.items():
        body = bytearray()
        last_record_count = 0
        last_extent = max(ext_map)
        for ext_num in sorted(ext_map):
            blocks, record_count = ext_map[ext_num]
            for b in blocks:
                start = reserved_bytes + b * block_bytes
                if start + block_bytes > len(flat):
                    break
                body.extend(flat[start : start + block_bytes])
            if ext_num == last_extent:
                last_record_count = record_count

        # Trim the body to the actual length. The last extent's
        # record_count tells us how many 128-byte records are valid in
        # the final extent; record_count==0 means the extent is full.
        if last_record_count and len(body):
            n_extents = last_extent + 1
            full_extents_bytes = (n_extents - 1) * EXTENT_RECORDS * RECORD_BYTES
            actual_len = full_extents_bytes + last_record_count * RECORD_BYTES
            body = body[:actual_len]

        files.append(CpmFile(user=user, name=name, ext=ext, body=bytes(body)))

    return files


def directory_looks_valid(flat: bytes, *, reserved_bytes: int = RESERVED_TRACK_BYTES) -> bool:
    """Quick fingerprint: does the disk's first directory entry look like
    a real CP/M file (printable name, valid user number)?"""
    if len(flat) < reserved_bytes + DIR_ENTRY_LEN:
        return False
    e = flat[reserved_bytes : reserved_bytes + DIR_ENTRY_LEN]
    if e[0] == DELETED:
        return True  # deleted entry is still valid CP/M
    if e[0] > 15:
        return False
    # Filename should be printable ASCII (allowing the high bit).
    name_bytes = bytes(b & 0x7F for b in e[1:12])
    return all(0x20 <= b < 0x7F or b == 0 for b in name_bytes)


def _count_valid_dir_entries(
    flat: bytes,
    reserved_bytes: int,
    n_dir_entries: int = N_DIR_ENTRIES,
) -> int:
    """Count plausible directory entries at `reserved_bytes`.

    Returns -1 if any entry's filename is non-printable (a strong signal
    that this isn't actually a directory).
    """
    if reserved_bytes + DIR_ENTRY_LEN * n_dir_entries > len(flat):
        return -1
    n = 0
    for i in range(n_dir_entries):
        e = flat[reserved_bytes + i * DIR_ENTRY_LEN : reserved_bytes + (i + 1) * DIR_ENTRY_LEN]
        if e[0] == DELETED or all(b == 0 for b in e):
            continue
        if e[0] > 15:
            continue  # disk label / time stamp / non-file
        name_bytes = bytes(b & 0x7F for b in e[1:12])
        if not all(0x20 <= b < 0x7F or b == 0 for b in name_bytes):
            return -1  # garbage name -> definitely not a directory here
        n += 1
    return n


def detect_reserved_offset(
    flat: bytes,
    *,
    sectors_per_track: int = 9,
    sides: int = 1,
    sector_bytes: int = 512,
) -> int:
    """Find the start of the CP/M directory by trying common reserved-track
    conventions for the disk geometry.

    +3 single-sided reserves 1 track (4608 bytes for 9-sector tracks).
    Double-sided ZXZVM-style boots reserve 2 (both sides of track 0 =
    9216 bytes). CPC reserves 0 (directory at offset 0). PCW variants
    sometimes reserve more. We pick whichever offset yields the most
    plausible directory entries.
    """
    track_bytes = sectors_per_track * sector_bytes
    candidates = [
        track_bytes,  # +3 SS: 1 reserved
        track_bytes * 2 if sides > 1 else track_bytes,  # +3 DS: 2 reserved
        0,  # CPC: 0 reserved
        track_bytes * 3,  # PCW: 3 reserved
    ]
    seen: set[int] = set()
    ordered: list[int] = []
    for r in candidates:
        if r not in seen:
            seen.add(r)
            ordered.append(r)

    best_offset = ordered[0]
    best_score = -1
    for r in ordered:
        score = _count_valid_dir_entries(flat, r)
        if score > best_score:
            best_score = score
            best_offset = r
    return best_offset
