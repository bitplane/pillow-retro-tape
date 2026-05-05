import pytest
from PIL import Image, UnidentifiedImageError

import pillow_retro_tape  # noqa: F401  (registers plugins)
from pillow_retro_tape.plus3dos import TYPE_CODE, make_plus3_header
from pillow_retro_tape.spectrum_dsk import extract_screen, parse_dsk

from ._helpers import make_extended_dsk, make_screen


def _layout_screen_into_sectors(file_bytes: bytes, n_sectors: int = 14) -> list[bytes]:
    """Pad and split a +3DOS file into N 512-byte sectors."""
    padded = file_bytes + b"\x00" * (n_sectors * 512 - len(file_bytes))
    return [padded[i * 512 : (i + 1) * 512] for i in range(n_sectors)]


def _make_screen_dsk_track(skewed: bool) -> tuple[bytes, bytes]:
    """Build a 14-sector track containing a +3DOS SCREEN$ file.

    Returns (full_dsk_bytes, expected_screen_bytes).
    """
    screen = make_screen(0xFF, 0x07)
    file_bytes = make_plus3_header(TYPE_CODE, len(screen), 0x4000) + screen
    sector_data = _layout_screen_into_sectors(file_bytes)
    # Sector IDs 1..14, but stored in skewed physical order so the parser
    # has to reorder them by ID to read the file correctly.
    if skewed:
        # Classic 2:1 skew on the first 9 -> realistic
        order = [1, 8, 2, 9, 3, 10, 4, 11, 5, 12, 6, 13, 7, 14]
    else:
        order = list(range(1, 15))
    sectors = [(sid, sector_data[sid - 1]) for sid in order]
    dsk = make_extended_dsk([sectors])
    return dsk, screen


def test_parse_dsk_collects_all_sectors():
    dsk, _ = _make_screen_dsk_track(skewed=False)
    img = parse_dsk(dsk)
    assert img.tracks == 1
    assert img.sides == 1
    assert len(img.sectors) == 14


def test_extract_screen_from_in_order_sectors():
    dsk, expected = _make_screen_dsk_track(skewed=False)
    assert extract_screen(dsk) == expected


def test_extract_screen_from_skewed_sectors():
    """Sector IDs are stored physically out of order — must be re-sorted."""
    dsk, expected = _make_screen_dsk_track(skewed=True)
    assert extract_screen(dsk) == expected


def test_extract_screen_raises_when_no_real_screen():
    # Build a DSK with a non-CODE file -> nothing extractable.
    body = b"\x00" * 256
    file_bytes = make_plus3_header(0, len(body), 5) + body  # type=0 (BASIC)
    sectors = _layout_screen_into_sectors(file_bytes, n_sectors=2)
    dsk = make_extended_dsk([[(1, sectors[0]), (2, sectors[1])]])
    with pytest.raises(ValueError):
        extract_screen(dsk)


def test_parse_dsk_rejects_bad_magic():
    bad = b"NOT A DSK FILE" + b"\x00" * 1000
    with pytest.raises(ValueError):
        parse_dsk(bad)


# --- Pillow integration ---------------------------------------------------


def test_pillow_open_synthetic_dsk(tmp_path):
    dsk, expected = _make_screen_dsk_track(skewed=True)
    p = tmp_path / "synth.dsk"
    p.write_bytes(dsk)
    img = Image.open(p)
    assert img.format == "ZXDSK"
    assert img.mode == "RGB"
    assert img.size == (256, 192)
    img.load()


def test_pillow_rejects_non_dsk(tmp_path):
    p = tmp_path / "junk.dsk"
    p.write_bytes(b"random content that is not a dsk")
    with pytest.raises(UnidentifiedImageError):
        Image.open(p)
