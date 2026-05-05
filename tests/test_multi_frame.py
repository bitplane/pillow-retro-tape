"""Tests for multi-frame seek/tell across TAP, TZX, and DSK plugins."""

import pytest
from PIL import Image, ImageSequence

import pillow_zx_spectrum  # noqa: F401  (registers plugins + decoder)
from pillow_zx_spectrum.blocks import TYPE_CODE
from pillow_zx_spectrum.plus3dos import TYPE_CODE as P3_CODE
from pillow_zx_spectrum.plus3dos import make_plus3_header
from pillow_zx_spectrum.spectrum_dsk import extract_screens as dsk_screens
from pillow_zx_spectrum.spectrum_screen import decode_screen_pixels
from pillow_zx_spectrum.spectrum_tap import extract_screens as tap_screens
from pillow_zx_spectrum.spectrum_tzx import extract_screens as tzx_screens

from ._helpers import (
    make_data_block,
    make_extended_dsk,
    make_header_block,
    make_screen,
    make_tap,
    make_tzx,
)


def _three_synthetic_screens() -> list[bytes]:
    return [
        make_screen(0xFF, 0x07),  # white on black
        make_screen(0xFF, 0x02),  # red on black
        make_screen(0xFF, 0x44),  # bright green on black
    ]


# --- TAP ---------------------------------------------------------------------


def _make_tap_with(screens: list[bytes]) -> bytes:
    blocks: list[bytes] = []
    for i, s in enumerate(screens):
        blocks.append(make_header_block(TYPE_CODE, f"scr{i}", 6912, 0x4000))
        blocks.append(make_data_block(s))
    return make_tap(*blocks)


def test_tap_extract_screens_returns_all_in_tape_order():
    screens = _three_synthetic_screens()
    tap = _make_tap_with(screens)
    assert tap_screens(tap) == screens


def test_tap_pillow_exposes_three_frames(tmp_path):
    screens = _three_synthetic_screens()
    p = tmp_path / "multi.tap"
    p.write_bytes(_make_tap_with(screens))
    img = Image.open(p)
    assert img.n_frames == 3
    assert img.tell() == 0
    img.load()
    assert img.tobytes() == decode_screen_pixels(screens[0])
    img.seek(2)
    assert img.tell() == 2
    img.load()
    assert img.tobytes() == decode_screen_pixels(screens[2])
    img.seek(1)
    img.load()
    assert img.tobytes() == decode_screen_pixels(screens[1])


def test_tap_seek_out_of_range_raises_eof(tmp_path):
    p = tmp_path / "one.tap"
    p.write_bytes(_make_tap_with([make_screen(0xFF, 0x07)]))
    img = Image.open(p)
    assert img.n_frames == 1
    with pytest.raises(EOFError):
        img.seek(1)
    with pytest.raises(EOFError):
        img.seek(-1)


def test_tap_image_sequence_iterator(tmp_path):
    screens = _three_synthetic_screens()
    p = tmp_path / "multi.tap"
    p.write_bytes(_make_tap_with(screens))
    img = Image.open(p)
    frames = [f.copy().tobytes() for f in ImageSequence.Iterator(img)]
    expected = [decode_screen_pixels(s) for s in screens]
    assert frames == expected


def test_tap_preserves_explicit_duplicate_screens():
    """Same screen loaded twice -> two frames (explicit loads aren't deduped)."""
    s = make_screen(0xFF, 0x07)
    tap = _make_tap_with([s, s])
    assert tap_screens(tap) == [s, s]


# --- TZX ---------------------------------------------------------------------


def _make_tzx_with(screens: list[bytes]) -> bytes:
    blocks: list[bytes] = []
    for i, s in enumerate(screens):
        blocks.append(make_header_block(TYPE_CODE, f"scr{i}", 6912, 0x4000))
        blocks.append(make_data_block(s))
    return make_tzx(*blocks)


def test_tzx_pillow_exposes_three_frames(tmp_path):
    screens = _three_synthetic_screens()
    p = tmp_path / "multi.tzx"
    p.write_bytes(_make_tzx_with(screens))
    img = Image.open(p)
    assert img.n_frames == 3
    img.seek(2)
    img.load()
    assert img.tobytes() == decode_screen_pixels(screens[2])


def test_tzx_extract_screens_in_tape_order():
    screens = _three_synthetic_screens()
    tzx = _make_tzx_with(screens)
    assert tzx_screens(tzx) == screens


# --- DSK ---------------------------------------------------------------------


def _layout_into_sectors(file_bytes: bytes, n_sectors: int) -> list[bytes]:
    padded = file_bytes + b"\x00" * (n_sectors * 512 - len(file_bytes))
    return [padded[i * 512 : (i + 1) * 512] for i in range(n_sectors)]


def _make_dsk_with(screens: list[bytes]) -> bytes:
    """Build a DSK with N SCREEN$ files, one per track (14 sectors each)."""
    tracks = []
    for s in screens:
        body = make_plus3_header(P3_CODE, len(s), 0x4000) + s
        sector_data = _layout_into_sectors(body, 14)
        tracks.append([(sid, sector_data[sid - 1]) for sid in range(1, 15)])
    return make_extended_dsk(tracks)


def test_dsk_extract_screens_returns_all():
    screens = _three_synthetic_screens()
    dsk = _make_dsk_with(screens)
    assert dsk_screens(dsk) == screens


def test_dsk_pillow_exposes_three_frames(tmp_path):
    screens = _three_synthetic_screens()
    p = tmp_path / "multi.dsk"
    p.write_bytes(_make_dsk_with(screens))
    img = Image.open(p)
    assert img.n_frames == 3
    img.seek(0)
    img.load()
    assert img.tobytes() == decode_screen_pixels(screens[0])
    img.seek(2)
    img.load()
    assert img.tobytes() == decode_screen_pixels(screens[2])


def test_dsk_seek_out_of_range_raises_eof(tmp_path):
    p = tmp_path / "two.dsk"
    p.write_bytes(_make_dsk_with(_three_synthetic_screens()[:2]))
    img = Image.open(p)
    with pytest.raises(EOFError):
        img.seek(2)
