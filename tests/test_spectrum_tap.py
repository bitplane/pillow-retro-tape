import struct

import pytest
from PIL import Image, UnidentifiedImageError

import pillow_zx_spectrum  # noqa: F401  (registers plugins)
from pillow_zx_spectrum.blocks import TYPE_CODE
from pillow_zx_spectrum.spectrum_tap import (
    _accept,
    extract_screen,
    iter_tap_blocks,
)

from ._helpers import (
    make_data_block,
    make_header_block,
    make_screen,
    make_tap,
)


def test_iter_tap_blocks_returns_each_record():
    screen = make_screen(0xFF, 0x07)
    tap = make_tap(
        make_header_block(TYPE_CODE, "scr", 6912, 0x4000),
        make_data_block(screen),
    )
    blocks = list(iter_tap_blocks(tap))
    assert len(blocks) == 2
    assert blocks[0].is_header()
    assert blocks[1].is_data()
    assert blocks[1].payload == screen


def test_extract_screen_from_synthetic_tap():
    screen = make_screen(0xFF, 0x07)
    tap = make_tap(
        make_header_block(TYPE_CODE, "scr", 6912, 0x4000),
        make_data_block(screen),
    )
    assert extract_screen(tap) == screen


def test_extract_screen_falls_back_to_6912_byte_block():
    screen = make_screen(0xAA, 0x07)
    tap = make_tap(
        make_header_block(TYPE_CODE, "p", 6912, 0x9C40),
        make_data_block(screen),
    )
    assert extract_screen(tap) == screen


def test_iter_tap_skips_truncated_block_silently():
    # Length says 100 bytes, only 5 follow -> treat as end-of-tape.
    bad = struct.pack("<H", 100) + b"\xff\x00\x00\x00\x00"
    assert list(iter_tap_blocks(bad)) == []


def test_iter_tap_skips_truncated_length_word():
    assert list(iter_tap_blocks(b"\x13")) == []


def test_iter_tap_skips_zero_length_block():
    bad = struct.pack("<H", 0)
    assert list(iter_tap_blocks(bad)) == []


def test_accept_fingerprint():
    # Real TAP starts: length=19 (0x0013), then flag.
    assert _accept(b"\x13\x00\x00")
    assert _accept(b"\x13\x00\xff")
    # Non-standard flag bytes are accepted at this stage (SAM Coupé and
    # custom-loader tapes use values other than 0x00/0xFF); _open does
    # the real validation.
    assert _accept(b"\x13\x00\x42")
    # Length too small to be a block
    assert not _accept(b"\x01\x00\x00")
    # Too short to fingerprint
    assert not _accept(b"\x13")


# --- Pillow integration ---------------------------------------------------


def test_pillow_open_synthetic_tap(tmp_path):
    screen = make_screen(0xFF, 0x07)
    tap = make_tap(
        make_header_block(TYPE_CODE, "scr", 6912, 0x4000),
        make_data_block(screen),
    )
    p = tmp_path / "synth.tap"
    p.write_bytes(tap)
    img = Image.open(p)
    assert img.format == "ZXTAP"
    assert img.mode == "RGB"
    assert img.size == (256, 192)
    assert img.info["pixel_aspect_ratio"] == (1, 1)
    img.load()


def test_pillow_rejects_malformed_tap(tmp_path):
    p = tmp_path / "junk.tap"
    p.write_bytes(struct.pack("<H", 1000) + b"\xff\x00\x00")  # truncated
    with pytest.raises(UnidentifiedImageError):
        Image.open(p)
