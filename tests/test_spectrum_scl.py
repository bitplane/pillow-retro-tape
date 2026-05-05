import pytest
from PIL import Image, UnidentifiedImageError

import pillow_retro_tape  # noqa: F401
from pillow_retro_tape.spectrum_scl import extract_screens
from pillow_retro_tape.tr_dos import TYPE_BASIC, TYPE_CODE

from ._helpers import make_scl, make_screen


def test_extract_screens_finds_all_code_6912_files():
    s1 = make_screen(0xFF, 0x07)
    s2 = make_screen(0xFF, 0x02)
    scl = make_scl(
        [
            ("LOADER", TYPE_BASIC, 10, 100, b"\x00" * 256),
            ("SCREEN1", TYPE_CODE, 0x4000, 6912, s1),
            ("SCREEN2", TYPE_CODE, 0x4000, 6912, s2),
        ]
    )
    assert extract_screens(scl) == [s1, s2]


def test_extract_screens_skips_code_files_of_wrong_size():
    scl = make_scl(
        [
            ("MAINCODE", TYPE_CODE, 0x6000, 8192, b"\x00" * 8192),
        ]
    )
    # File is recognised but has no extractable screen -> null-screen fallback.
    assert extract_screens(scl) == [bytes(6912)]


def test_pillow_open_scl(tmp_path):
    s = make_screen(0xFF, 0x07)
    scl = make_scl([("SCREEN", TYPE_CODE, 0x4000, 6912, s)])
    p = tmp_path / "synth.scl"
    p.write_bytes(scl)
    img = Image.open(p)
    assert img.format == "ZXSCL"
    assert img.size == (256, 192)
    img.load()


def test_pillow_rejects_bad_magic(tmp_path):
    p = tmp_path / "junk.scl"
    p.write_bytes(b"not an scl" + b"\x00" * 100)
    with pytest.raises(UnidentifiedImageError):
        Image.open(p)


def test_pillow_multi_frame(tmp_path):
    s1 = make_screen(0xFF, 0x07)
    s2 = make_screen(0xFF, 0x02)
    scl = make_scl(
        [
            ("SCREEN1", TYPE_CODE, 0x4000, 6912, s1),
            ("SCREEN2", TYPE_CODE, 0x4000, 6912, s2),
        ]
    )
    p = tmp_path / "two.scl"
    p.write_bytes(scl)
    img = Image.open(p)
    assert img.n_frames == 2
