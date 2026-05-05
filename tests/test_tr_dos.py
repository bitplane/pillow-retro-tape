import pytest

from pillow_retro_tape.tr_dos import (
    TYPE_BASIC,
    TYPE_CODE,
    parse_scl_files,
    parse_trd_files,
)

from ._helpers import make_screen, make_scl, make_trd


def test_parse_scl_yields_files_in_order():
    body_a = b"\x42" * 256
    body_b = b"\x43" * 512
    scl = make_scl(
        [
            ("LOADER", TYPE_BASIC, 10, 100, body_a),
            ("SCREEN", TYPE_CODE, 0x4000, 6912, body_b),
        ]
    )
    files = list(parse_scl_files(scl))
    assert [f.name for f in files] == ["LOADER", "SCREEN"]
    assert files[0].type == TYPE_BASIC
    assert files[0].body == body_a
    assert files[1].type == TYPE_CODE
    assert files[1].param2 == 6912
    assert files[1].body == body_b


def test_parse_scl_rejects_bad_magic():
    with pytest.raises(ValueError):
        list(parse_scl_files(b"not an scl file......"))


def test_parse_trd_yields_files_with_body_at_declared_track():
    screen = make_screen(0xFF, 0x07)
    # Pad to a multiple of 256 (already is: 6912 = 27*256).
    trd = make_trd([("SCR", TYPE_CODE, 0x4000, 6912, screen)])
    files = list(parse_trd_files(trd))
    assert len(files) == 1
    assert files[0].name == "SCR"
    assert files[0].type == TYPE_CODE
    assert files[0].param2 == 6912
    assert files[0].body == screen


def test_parse_trd_handles_multiple_files():
    bodies = [b"\x11" * 256, b"\x22" * 512, b"\x33" * 256]
    trd = make_trd(
        [
            ("F1", TYPE_BASIC, 0, 0, bodies[0]),
            ("F2", TYPE_CODE, 0x6000, 512, bodies[1]),
            ("F3", TYPE_CODE, 0x8000, 256, bodies[2]),
        ]
    )
    files = list(parse_trd_files(trd))
    assert len(files) == 3
    assert [f.body for f in files] == bodies


def test_parse_trd_stops_at_zero_filename():
    screen = make_screen(0xFF, 0x07)
    trd = make_trd([("ONLY", TYPE_CODE, 0x4000, 6912, screen)])
    files = list(parse_trd_files(trd))
    # 128 entries available, but only 1 used; rest start with 0x00 -> end-of-dir.
    assert len(files) == 1
