"""Generate a colour-bar SCREEN$ used as a golden test fixture.

Layout:
    Top half    (rows  0..11): 8 vertical bars, ink colours 0..7, no bright.
    Bottom half (rows 12..23): same colours with BRIGHT.

Each bar is 4 character columns (32 pixels) wide. All pixels are set, so
each 8x8 cell shows its ink colour solid.

Usage: python scripts/make_test_scr.py tests/data/colorbars.scr
"""

import sys
from pathlib import Path


def make_colorbars() -> bytes:
    pixels = bytes([0xFF] * 6144)  # all bits on -> ink colour everywhere
    attrs = bytearray(768)
    for char_y in range(24):
        bright = 0x40 if char_y >= 12 else 0x00
        for char_x in range(32):
            ink = char_x // 4  # 0..7 across 8 bands
            paper = 0  # black
            attrs[char_y * 32 + char_x] = bright | (paper << 3) | ink
    return pixels + bytes(attrs)


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    out = Path(sys.argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(make_colorbars())
    print(f"wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
