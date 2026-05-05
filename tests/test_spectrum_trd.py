import pytest
from PIL import Image, UnidentifiedImageError

import pillow_retro_tape  # noqa: F401
from pillow_retro_tape.spectrum_trd import extract_screens
from pillow_retro_tape.tr_dos import TYPE_BASIC, TYPE_CODE

from ._helpers import make_screen, make_trd


def test_extract_screens_from_trd():
    s = make_screen(0xFF, 0x07)
    trd = make_trd(
        [
            ("LOADER", TYPE_BASIC, 10, 100, b"\x00" * 256),
            ("SCREEN", TYPE_CODE, 0x4000, 6912, s),
        ]
    )
    assert extract_screens(trd) == [s]


def test_pillow_open_trd(tmp_path):
    s = make_screen(0xFF, 0x07)
    trd = make_trd([("SCREEN", TYPE_CODE, 0x4000, 6912, s)])
    p = tmp_path / "synth.trd"
    p.write_bytes(trd)
    img = Image.open(p)
    assert img.format == "ZXTRD"
    img.load()


def test_pillow_rejects_too_short(tmp_path):
    p = tmp_path / "short.trd"
    p.write_bytes(b"\x00" * 100)
    with pytest.raises(UnidentifiedImageError):
        Image.open(p)


def test_pillow_rejects_missing_trdos_magic(tmp_path):
    p = tmp_path / "bad.trd"
    # 64K of zeros: long enough but missing the 0x10 magic at 0x8E7.
    p.write_bytes(b"\x00" * 0x10000)
    with pytest.raises(UnidentifiedImageError):
        Image.open(p)
