from pillow_retro_tape.palette import (
    BRIGHT_LEVEL,
    NORMAL_LEVEL,
    SPECTRUM_BRIGHT,
    SPECTRUM_NORMAL,
)


def test_palette_lengths():
    assert len(SPECTRUM_NORMAL) == 8
    assert len(SPECTRUM_BRIGHT) == 8


def test_black_is_black_at_both_levels():
    assert SPECTRUM_NORMAL[0] == (0, 0, 0)
    assert SPECTRUM_BRIGHT[0] == (0, 0, 0)


def test_grb_bit_ordering():
    # Index bits: bit 0 = blue, bit 1 = red, bit 2 = green
    assert SPECTRUM_NORMAL[1] == (0, 0, NORMAL_LEVEL)  # blue
    assert SPECTRUM_NORMAL[2] == (NORMAL_LEVEL, 0, 0)  # red
    assert SPECTRUM_NORMAL[4] == (0, NORMAL_LEVEL, 0)  # green
    assert SPECTRUM_NORMAL[6] == (NORMAL_LEVEL, NORMAL_LEVEL, 0)  # yellow


def test_white_uses_full_brightness_level():
    assert SPECTRUM_NORMAL[7] == (NORMAL_LEVEL, NORMAL_LEVEL, NORMAL_LEVEL)
    assert SPECTRUM_BRIGHT[7] == (BRIGHT_LEVEL, BRIGHT_LEVEL, BRIGHT_LEVEL)
