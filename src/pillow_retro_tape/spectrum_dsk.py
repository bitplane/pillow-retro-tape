"""Pillow plugin for ZX Spectrum +3 / Amstrad CPC disk images (.dsk).

Two on-disk variants:
- "Standard" CPC DSK: magic ``MV - CPC``. All tracks are the same size,
  given by a 16-bit field in the disk-info header. Sector size is fixed
  per track via the size code.
- "Extended" CPC DSK: magic ``EXTENDED CPC DSK File``. Tracks may differ
  in size; the disk-info header carries a track size table (one byte per
  track-side, in 256-byte units; 0 means the track is absent). Sector
  sizes are read from each sector's info entry (used for protected disks
  with weak/long sectors).

Layout:
    [0..255]   Disk-Info (256 bytes)
    [256..]    Per-track blocks, each = 256-byte Track-Info + sectors

Each Track-Info block holds:
    16   track number
    17   side number
    20   sector size code (size = 128 << code)
    21   number of sectors
    24+  Sector-Info List, 8 bytes per sector:
            +0 track, +1 side, +2 sector ID (R), +3 size code,
            +4..5 FDC status, +6..7 actual length (extended DSK only)

After Track-Info, the sectors are stored in physical (on-disk) order. To
read a file, sectors must be re-sorted by sector ID per track.

Screen extraction: parse to logical sectors -> concatenate -> scan for
``PLUS3DOS\\x1A`` headers at sector boundaries -> first CODE file with
length 6912 is the loading screen.
"""

import struct

from PIL import Image

from .cpm import directory_looks_valid, list_files
from .disk import DiskImage, Sector
from .pillow_screen import ScreenSequenceImageFile
from .plus3dos import TYPE_CODE, find_plus3_files, parse_at
from .spectrum_screen import SCREEN_BYTES

DSK_MAGIC_EXT = b"EXTENDED CPC DSK File"
DSK_MAGIC_STD = b"MV - CPC"
DISK_INFO_LEN = 256
TRACK_INFO_LEN = 256
TRACK_INFO_MAGIC = b"Track-Info"


def parse_dsk(data: bytes) -> DiskImage:
    if len(data) < DISK_INFO_LEN:
        raise ValueError("DSK file too short")
    extended = data.startswith(DSK_MAGIC_EXT)
    if not extended and not data.startswith(DSK_MAGIC_STD):
        raise ValueError("not a CPC DSK file")

    n_tracks = data[48]
    n_sides = data[49]
    n_track_blocks = n_tracks * n_sides

    if extended:
        sizes = list(data[52 : 52 + n_track_blocks])
        track_sizes = [s * 256 for s in sizes]
    else:
        std = struct.unpack_from("<H", data, 50)[0]
        track_sizes = [std] * n_track_blocks

    sectors: list[Sector] = []
    offset = DISK_INFO_LEN
    for size in track_sizes:
        if size == 0:
            continue
        if offset + size > len(data):
            raise ValueError(f"track at offset {offset} runs past EOF")
        sectors.extend(_parse_track(data[offset : offset + size], extended))
        offset += size

    return DiskImage(tracks=n_tracks, sides=n_sides, sectors=sectors)


def _parse_track(track_data: bytes, extended: bool) -> list[Sector]:
    if not track_data.startswith(TRACK_INFO_MAGIC):
        raise ValueError("missing Track-Info marker")
    track = track_data[16]
    side = track_data[17]
    n_sectors = track_data[21]

    out: list[Sector] = []
    cursor = TRACK_INFO_LEN
    for s in range(n_sectors):
        info = track_data[24 + s * 8 : 24 + s * 8 + 8]
        if len(info) < 8:
            raise ValueError("truncated sector-info entry")
        sector_id = info[2]
        size_code = info[3]
        if extended:
            actual_len = info[6] | (info[7] << 8)
            if actual_len == 0:
                actual_len = 128 << size_code
        else:
            actual_len = 128 << size_code
        if cursor + actual_len > len(track_data):
            raise ValueError(f"sector {sector_id} runs past track end")
        out.append(
            Sector(
                track=track,
                side=side,
                sector_id=sector_id,
                data=bytes(track_data[cursor : cursor + actual_len]),
            )
        )
        cursor += actual_len
    return out


SCREEN_LOAD_ADDR = 0x4000

# Filename hints (uppercase, substring match) that strongly suggest a
# loading screen. Ranked first so they show up as frame 0.
_SCREEN_NAME_HINTS = ("SCR", "PIC", "TITL", "LOAD", "INTRO", "FRONT", "MAIN")


def _is_screen_shaped(plus3_file) -> bool:
    return (
        plus3_file is not None
        and plus3_file.type == TYPE_CODE
        and plus3_file.length == SCREEN_BYTES
        and len(plus3_file.body) == SCREEN_BYTES
    )


def _screen_priority(name: str, ext: str, addr: int) -> int:
    """Lower = more likely to be a loading screen.

    Filename hints (SCR/PIC/TITL/LOAD/...) win over the canonical $4000
    load address, which wins over other 6912-byte CODE files.
    """
    upper = (name + ext).upper()
    if any(h in upper for h in _SCREEN_NAME_HINTS):
        return 0
    if addr == SCREEN_LOAD_ADDR:
        return 1
    return 2


def extract_screens(dsk_data: bytes) -> list[bytes]:
    """Return every plausible 6912-byte SCREEN$ in the DSK, ranked.

    Frame ordering: filename-hinted files first (SCR/PIC/TITL/...),
    then files loaded to $4000, then any other 6912-byte CODE file.
    Within each tier, disk order is preserved.

    Two strategies for finding files:
    1. If the disk has a CP/M directory, walk it and reconstruct each
       file from its allocation block list (handles fragmentation).
    2. Otherwise (raw +3DOS written directly to disk, no CP/M FS), scan
       sector-aligned positions for the +3DOS magic and assume
       contiguous allocation.
    """
    img = parse_dsk(dsk_data)
    flat = img.flat()
    candidates: list[tuple[int, int, bytes]] = []  # (priority, disk_order, body)

    if directory_looks_valid(flat):
        for order, cpm_file in enumerate(list_files(flat)):
            f = parse_at(cpm_file.body, 0)
            if _is_screen_shaped(f):
                pri = _screen_priority(cpm_file.name, cpm_file.ext, f.param1)
                candidates.append((pri, order, f.body))
    if not candidates:
        # Fallback: raw magic-scan with no filename info (priority by addr).
        for order, f in enumerate(find_plus3_files(flat)):
            if _is_screen_shaped(f):
                pri = _screen_priority("", "", f.param1)
                candidates.append((pri, order, f.body))

    candidates.sort(key=lambda x: (x[0], x[1]))
    return [body for _, _, body in candidates]


def extract_screen(dsk_data: bytes) -> bytes:
    """Return the first SCREEN$ file (preserved for single-frame use)."""
    screens = extract_screens(dsk_data)
    if not screens:
        raise ValueError("no SCREEN$ file found in DSK image")
    return screens[0]


# --- Pillow plugin --------------------------------------------------------


class ZXDSKImageFile(ScreenSequenceImageFile):
    format = "ZXDSK"
    format_description = "ZX Spectrum +3 / Amstrad CPC disk image"

    def _open(self):
        head = self.fp.read(len(DSK_MAGIC_EXT))
        self.fp.seek(0)
        if not (head.startswith(DSK_MAGIC_STD) or head.startswith(DSK_MAGIC_EXT)):
            raise SyntaxError("not a CPC DSK file")
        data = self.fp.read()
        try:
            screens = extract_screens(data)
        except ValueError as e:
            raise SyntaxError(f"failed to parse DSK: {e}") from e
        self._set_frames(screens)


def _accept(prefix: bytes) -> bool:
    return prefix.startswith(DSK_MAGIC_STD) or prefix.startswith(DSK_MAGIC_EXT[:8])


def register() -> None:
    Image.register_open(ZXDSKImageFile.format, ZXDSKImageFile, _accept)
    Image.register_extension(ZXDSKImageFile.format, ".dsk")
