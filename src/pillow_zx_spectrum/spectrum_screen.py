"""Decode a ZX Spectrum SCREEN$ (6912 bytes) to an RGB image.

Layout:
- bytes 0..6143: pixel data, 256x192 monochrome with the Spectrum's
  thirds-interleaved address scheme.
- bytes 6144..6911: 32x24 attribute cells (1 byte per 8x8 cell).

Pixel address for (x, y), x in 0..255, y in 0..191:
    offset = ((y & 0xC0) << 5) | ((y & 0x07) << 8) | ((y & 0x38) << 2) | (x >> 3)
    bit    = 7 - (x & 7)

Attribute byte: FLASH(7) BRIGHT(6) PAPER(5..3) INK(2..0).
FLASH is currently rendered in its non-flashed state.
"""

from PIL import Image

from .palette import SPECTRUM_BRIGHT, SPECTRUM_NORMAL

SCREEN_BYTES = 6912
PIXEL_BYTES = 6144
WIDTH = 256
HEIGHT = 192


def decode_screen_pixels(data: bytes) -> bytes:
    """Decode a 6912-byte SCREEN$ to a 256*192*3 RGB byte buffer."""
    if len(data) != SCREEN_BYTES:
        raise ValueError(f"expected {SCREEN_BYTES} bytes, got {len(data)}")

    pixels = data[:PIXEL_BYTES]
    attrs = data[PIXEL_BYTES:]
    out = bytearray(WIDTH * HEIGHT * 3)

    for y in range(HEIGHT):
        row_base = ((y & 0xC0) << 5) | ((y & 0x07) << 8) | ((y & 0x38) << 2)
        attr_row = (y >> 3) * 32
        out_row = y * WIDTH * 3
        for cx in range(32):
            byte = pixels[row_base + cx]
            attr = attrs[attr_row + cx]
            ink = attr & 0x07
            paper = (attr >> 3) & 0x07
            pal = SPECTRUM_BRIGHT if (attr & 0x40) else SPECTRUM_NORMAL
            ink_r, ink_g, ink_b = pal[ink]
            paper_r, paper_g, paper_b = pal[paper]
            out_x = out_row + cx * 24
            for bit in range(8):
                if (byte >> (7 - bit)) & 1:
                    out[out_x] = ink_r
                    out[out_x + 1] = ink_g
                    out[out_x + 2] = ink_b
                else:
                    out[out_x] = paper_r
                    out[out_x + 1] = paper_g
                    out[out_x + 2] = paper_b
                out_x += 3

    return bytes(out)


def decode_screen(data: bytes) -> Image.Image:
    """Decode a 6912-byte SCREEN$ to a 256x192 RGB Pillow image."""
    img = Image.frombytes("RGB", (WIDTH, HEIGHT), decode_screen_pixels(data))
    img.info["pixel_aspect_ratio"] = (1, 1)
    return img
