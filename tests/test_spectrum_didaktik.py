import pytest
from PIL import Image, UnidentifiedImageError

import pillow_zx_spectrum  # noqa: F401
from pillow_zx_spectrum.didaktik import (
    DIR_SECTORS,
    FAT_SECTORS,
    SDOS_MARKER,
    SDOS_MARKER_OFFSET,
    SECTOR_BYTES,
    DidaktikGeometry,
    fat12_get,
    parse_didaktik_files,
    parse_geometry,
)
from pillow_zx_spectrum.spectrum_didaktik import extract_screens

from ._helpers import make_screen

# --- Synthetic image builder ---------------------------------------------


def _make_boot_sector(*, tracks: int = 80, sides: int = 2, sectors_per_track: int = 9) -> bytes:
    boot = bytearray(SECTOR_BYTES)
    boot[177] = 0x10 if sides == 2 else 0x00
    boot[178] = tracks
    boot[179] = sectors_per_track
    boot[SDOS_MARKER_OFFSET : SDOS_MARKER_OFFSET + 4] = SDOS_MARKER
    return bytes(boot)


def _fat_set(fat: bytearray, idx: int, value: int) -> None:
    """Write one MDOS-packed 12-bit FAT entry."""
    pair = idx // 2
    off = pair * 3
    if off + 2 >= len(fat):
        return
    if idx & 1:
        # entry B: low byte at off+2, high nibble in low nibble of off+1
        fat[off + 2] = value & 0xFF
        fat[off + 1] = (fat[off + 1] & 0xF0) | ((value >> 8) & 0x0F)
    else:
        # entry A: low byte at off, high nibble in high nibble of off+1
        fat[off] = value & 0xFF
        fat[off + 1] = (fat[off + 1] & 0x0F) | (((value >> 8) & 0x0F) << 4)


def _make_dir_entry(type_: str, name: str, length: int, param1: int, first_sector: int) -> bytes:
    e = bytearray(0xE5 for _ in range(32))
    e[0] = ord(type_)
    name_bytes = name.encode("ascii")[:10]
    e[1:11] = name_bytes + b"\x00" * (10 - len(name_bytes))
    e[11] = length & 0xFF
    e[12] = (length >> 8) & 0xFF
    e[13] = param1 & 0xFF
    e[14] = (param1 >> 8) & 0xFF
    e[15] = 0
    e[16] = 0
    e[17] = first_sector & 0xFF
    e[18] = (first_sector >> 8) & 0xFF
    e[19] = 0
    e[20] = 0
    e[21] = (length >> 16) & 0xFF
    return bytes(e)


def _make_image(
    files: list[tuple[str, str, int, bytes]],
    *,
    tracks: int = 80,
    sectors_per_track: int = 9,
    sides: int = 2,
) -> bytes:
    """Build a complete D80 image. Each file = (type, name, load_addr, body).
    Files are placed contiguously starting at sector 14.
    """
    geometry = DidaktikGeometry(tracks=tracks, sides=sides, sectors_per_track=sectors_per_track)
    out = bytearray(geometry.total_bytes)
    out[0:SECTOR_BYTES] = _make_boot_sector(tracks=tracks, sides=sides, sectors_per_track=sectors_per_track)

    fat_bytes = (FAT_SECTORS[1] - FAT_SECTORS[0]) * SECTOR_BYTES
    fat = bytearray(fat_bytes)

    cursor = 14  # first data sector
    dir_offset = DIR_SECTORS[0] * SECTOR_BYTES
    for i, (type_, name, addr, body) in enumerate(files):
        sectors_needed = max(1, (len(body) + SECTOR_BYTES - 1) // SECTOR_BYTES)
        # Write body to sectors [cursor..cursor+sectors_needed)
        for s in range(sectors_needed):
            sector_idx = cursor + s
            chunk = body[s * SECTOR_BYTES : (s + 1) * SECTOR_BYTES]
            sector_off = sector_idx * SECTOR_BYTES
            out[sector_off : sector_off + len(chunk)] = chunk
            # FAT chain: link to next, last one is EOF marker
            if s < sectors_needed - 1:
                _fat_set(fat, sector_idx, sector_idx + 1)
            else:
                tail = len(body) % SECTOR_BYTES
                _fat_set(fat, sector_idx, 0xE00 | tail)
        # Directory entry
        out[dir_offset + i * 32 : dir_offset + (i + 1) * 32] = _make_dir_entry(type_, name, len(body), addr, cursor)
        cursor += sectors_needed

    fat_offset = FAT_SECTORS[0] * SECTOR_BYTES
    out[fat_offset : fat_offset + fat_bytes] = fat
    return bytes(out)


# --- FAT12 packing ------------------------------------------------------


def test_fat12_packing_round_trip():
    fat = bytearray(12)
    _fat_set(fat, 0, 0x123)
    _fat_set(fat, 1, 0x456)
    _fat_set(fat, 4, 0xE15)
    _fat_set(fat, 5, 0xABC)
    assert fat12_get(fat, 0) == 0x123
    assert fat12_get(fat, 1) == 0x456
    assert fat12_get(fat, 4) == 0xE15
    assert fat12_get(fat, 5) == 0xABC


# --- Boot sector --------------------------------------------------------


def test_parse_geometry_reads_sdos_disk():
    boot = _make_boot_sector(tracks=80, sides=2, sectors_per_track=10)
    g = parse_geometry(boot)
    assert g.tracks == 80
    assert g.sides == 2
    assert g.sectors_per_track == 10
    assert g.total_sectors == 80 * 2 * 10


def test_parse_geometry_rejects_missing_sdos():
    with pytest.raises(ValueError):
        parse_geometry(b"\x00" * SECTOR_BYTES)


# --- Directory + file reconstruction -----------------------------------


def test_parse_files_reconstructs_contiguous_chain():
    s = make_screen(0xFF, 0x07)
    img = _make_image([("B", "screen", 0x4000, s)])
    files = list(parse_didaktik_files(img))
    assert len(files) == 1
    assert files[0].type == "B"
    assert files[0].name == "screen"
    assert files[0].length == 6912
    assert files[0].param1 == 0x4000
    assert files[0].body == s


def test_parse_files_handles_multiple_entries():
    s = make_screen(0xFF, 0x02)
    img = _make_image(
        [
            ("P", "loader", 0, b"\x00" * 100),
            ("B", "screen", 0x4000, s),
            ("B", "code", 0x8000, b"\x42" * 4096),
        ]
    )
    files = list(parse_didaktik_files(img))
    names = [f.name for f in files]
    assert "loader" in names and "screen" in names and "code" in names


def test_extract_screens_finds_b_file_at_4000():
    s = make_screen(0xFF, 0x07)
    img = _make_image([("B", "screen", 0x4000, s)])
    assert extract_screens(img) == [s]


def test_extract_screens_returns_empty_for_basic_only():
    img = _make_image([("P", "loader", 0, b"\x00" * 100)])
    assert extract_screens(img) == []


# --- Pillow integration ------------------------------------------------


def test_pillow_open_d80(tmp_path):
    s = make_screen(0xFF, 0x07)
    p = tmp_path / "synth.d80"
    p.write_bytes(_make_image([("B", "screen", 0x4000, s)]))
    img = Image.open(p)
    assert img.format == "ZXDIDAKTIK"
    assert img.size == (256, 192)
    img.load()


def test_pillow_open_d40_extension(tmp_path):
    s = make_screen(0xFF, 0x07)
    p = tmp_path / "synth.d40"
    p.write_bytes(_make_image([("B", "screen", 0x4000, s)], tracks=40))
    img = Image.open(p)
    assert img.format == "ZXDIDAKTIK"


def test_pillow_rejects_non_didaktik(tmp_path):
    p = tmp_path / "junk.d80"
    p.write_bytes(b"\x00" * 100000)
    with pytest.raises(UnidentifiedImageError):
        Image.open(p)
