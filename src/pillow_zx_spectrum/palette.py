"""ZX Spectrum 16-colour palette.

The Spectrum has 8 base colours, each available at two brightness levels.
Attribute bytes encode colour as a 3-bit index where the bits are G, R, B
(MSB to LSB), e.g. 0b110 = yellow (G+R, no B).

The exact RGB values are a convention; we use FUSE/Spectaculator's:
0xD7 for normal, 0xFF for bright.
"""

NORMAL_LEVEL = 0xD7
BRIGHT_LEVEL = 0xFF

RGB = tuple[int, int, int]


def _palette(level: int) -> tuple[RGB, ...]:
    return (
        (0, 0, 0),  # 0 black
        (0, 0, level),  # 1 blue
        (level, 0, 0),  # 2 red
        (level, 0, level),  # 3 magenta
        (0, level, 0),  # 4 green
        (0, level, level),  # 5 cyan
        (level, level, 0),  # 6 yellow
        (level, level, level),  # 7 white
    )


SPECTRUM_NORMAL: tuple[RGB, ...] = _palette(NORMAL_LEVEL)
SPECTRUM_BRIGHT: tuple[RGB, ...] = _palette(BRIGHT_LEVEL)
