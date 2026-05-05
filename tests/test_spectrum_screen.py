import pytest

from pillow_retro_tape.palette import (
    BRIGHT_LEVEL,
    NORMAL_LEVEL,
    SPECTRUM_BRIGHT,
    SPECTRUM_NORMAL,
)
from pillow_retro_tape.spectrum_screen import (
    HEIGHT,
    WIDTH,
    decode_screen,
    decode_screen_pixels,
)

from ._helpers import make_screen, with_pixel_byte


def get_pixel(buf: bytes, x: int, y: int) -> tuple[int, int, int]:
    i = (y * WIDTH + x) * 3
    return buf[i], buf[i + 1], buf[i + 2]


def test_wrong_size_raises():
    with pytest.raises(ValueError):
        decode_screen_pixels(b"\x00" * 6911)
    with pytest.raises(ValueError):
        decode_screen_pixels(b"\x00" * 6913)


def test_decode_screen_returns_image_with_par():
    img = decode_screen(make_screen())
    assert img.mode == "RGB"
    assert img.size == (WIDTH, HEIGHT)
    assert img.info["pixel_aspect_ratio"] == (1, 1)


def test_all_zero_pixels_paint_paper():
    # paper=white(7), ink=black(0) -> attr = 0b00111000 = 0x38
    buf = decode_screen_pixels(make_screen(pixel_byte=0x00, attr_byte=0x38))
    assert get_pixel(buf, 0, 0) == SPECTRUM_NORMAL[7]
    assert get_pixel(buf, 255, 191) == SPECTRUM_NORMAL[7]


def test_all_one_pixels_paint_ink():
    # paper=black(0), ink=red(2) -> attr = 0x02
    buf = decode_screen_pixels(make_screen(pixel_byte=0xFF, attr_byte=0x02))
    assert get_pixel(buf, 0, 0) == SPECTRUM_NORMAL[2]
    assert get_pixel(buf, 100, 100) == SPECTRUM_NORMAL[2]


def test_bright_attribute_uses_bright_palette():
    # ink=white, bright on -> attr = 0x47
    buf = decode_screen_pixels(make_screen(pixel_byte=0xFF, attr_byte=0x47))
    assert get_pixel(buf, 0, 0) == SPECTRUM_BRIGHT[7]
    assert SPECTRUM_BRIGHT[7] == (BRIGHT_LEVEL, BRIGHT_LEVEL, BRIGHT_LEVEL)
    assert SPECTRUM_NORMAL[7] == (NORMAL_LEVEL, NORMAL_LEVEL, NORMAL_LEVEL)


def test_flash_attribute_is_ignored_for_now():
    # FLASH set, otherwise red ink on black paper, all-on pixels
    buf_flash = decode_screen_pixels(make_screen(pixel_byte=0xFF, attr_byte=0x82))
    buf_no_flash = decode_screen_pixels(make_screen(pixel_byte=0xFF, attr_byte=0x02))
    assert buf_flash == buf_no_flash


def test_msb_is_leftmost_pixel():
    # 0x80 = bit 7 only -> leftmost pixel of cell is ink, rest is paper.
    # attr: paper=white(7), ink=black(0) -> 0x38
    data = with_pixel_byte(offset=0, value=0x80, attr_byte=0x38)
    buf = decode_screen_pixels(data)
    assert get_pixel(buf, 0, 0) == SPECTRUM_NORMAL[0]  # ink
    assert get_pixel(buf, 1, 0) == SPECTRUM_NORMAL[7]  # paper


@pytest.mark.parametrize(
    "offset, expected_y",
    [
        # Address bits: thirds(2) | sub-row(3) | char-row(3) | x_byte(5).
        # So sub-row lives in the high byte (offset 256) and char-row at
        # offset 32 in the low byte.
        (0, 0),  # third 0, char_row 0, sub-row 0
        (32, 8),  # third 0, char_row 1, sub-row 0
        (256, 1),  # third 0, char_row 0, sub-row 1
        (2048, 64),  # third 1, char_row 0, sub-row 0
        (4096, 128),  # third 2, char_row 0, sub-row 0
        (4096 + 256 + 32, 128 + 1 + 8),  # third 2, sub-row 1, char_row 1
    ],
)
def test_address_interleave(offset, expected_y):
    # Single byte at `offset` should appear at `expected_y` only.
    # ink=black(0), paper=white(7) so a non-zero pixel byte is darker.
    data = with_pixel_byte(offset=offset, value=0xFF, attr_byte=0x38)
    buf = decode_screen_pixels(data)
    # First column of cell at expected_y is ink
    assert get_pixel(buf, 0, expected_y) == SPECTRUM_NORMAL[0]
    # Adjacent rows in the same cell are paper (only this scanline lit)
    if expected_y + 1 < HEIGHT:
        assert get_pixel(buf, 0, expected_y + 1) == SPECTRUM_NORMAL[7]
    if expected_y > 0:
        assert get_pixel(buf, 0, expected_y - 1) == SPECTRUM_NORMAL[7]


def test_attribute_cell_boundary():
    # Attributes are 8x8 cells. Set cell (1, 0) ink=red, others ink=black on
    # white paper, all pixel bits on.
    pixels = bytes([0xFF] * 6144)
    attrs = bytearray([0x38] * 768)  # white paper, black ink
    attrs[1] = 0x3A  # cell (1, 0): white paper, red ink
    data = pixels + bytes(attrs)
    buf = decode_screen_pixels(data)
    assert get_pixel(buf, 7, 0) == SPECTRUM_NORMAL[0]  # cell (0,0) ink black
    assert get_pixel(buf, 8, 0) == SPECTRUM_NORMAL[2]  # cell (1,0) ink red
    assert get_pixel(buf, 15, 7) == SPECTRUM_NORMAL[2]  # still cell (1,0)
    assert get_pixel(buf, 8, 8) == SPECTRUM_NORMAL[0]  # cell (1,1) ink black
