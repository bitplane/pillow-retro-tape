import pytest
from PIL import Image, UnidentifiedImageError

import pillow_retro_tape  # noqa: F401
from pillow_retro_tape.mgt import (
    TYPE_BASIC,
    TYPE_CODE,
    TYPE_SCREEN,
    parse_mgt_files,
)
from pillow_retro_tape.spectrum_mgt import extract_screens

from ._helpers import make_mgt, make_screen


def test_parse_mgt_yields_files_in_directory_order():
    s = make_screen(0xFF, 0x07)
    mgt = make_mgt(
        [
            ("Loader", TYPE_BASIC, 10, 76, b"\x00" * 76),
            ("ScrPic", TYPE_SCREEN, 0x4000, 6912, s),
        ]
    )
    files = list(parse_mgt_files(mgt))
    assert [f.name for f in files] == ["Loader", "ScrPic"]
    assert files[0].type == TYPE_BASIC
    assert files[1].type == TYPE_SCREEN
    assert files[1].body == s


def test_extract_screens_returns_screen_payload():
    s = make_screen(0xFF, 0x07)
    mgt = make_mgt([("Picture", TYPE_SCREEN, 0x4000, 6912, s)])
    screens = extract_screens(mgt)
    assert screens == [s]


def test_extract_screens_handles_code_at_4000():
    s = make_screen(0xFF, 0x02)
    mgt = make_mgt([("Loader", TYPE_BASIC, 10, 76, b"\x00" * 76), ("MainCode", TYPE_CODE, 0x4000, 6912, s)])
    screens = extract_screens(mgt)
    assert screens == [s]


def test_pillow_open_mgt(tmp_path):
    s = make_screen(0xFF, 0x07)
    mgt = make_mgt([("Picture", TYPE_SCREEN, 0x4000, 6912, s)])
    p = tmp_path / "synth.mgt"
    p.write_bytes(mgt)
    img = Image.open(p)
    assert img.format == "ZXMGT"
    assert img.size == (256, 192)


def test_pillow_rejects_garbage(tmp_path):
    p = tmp_path / "junk.mgt"
    p.write_bytes(b"\xff" * 100000)  # not a valid directory
    with pytest.raises(UnidentifiedImageError):
        Image.open(p)
