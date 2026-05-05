"""Pillow plugin for ZX Spectrum SCREEN$ (.scr) files.

A .scr is exactly 6912 bytes with no magic header. We identify it by file
extension and validate the size in `_open()`.
"""

from PIL import Image, ImageFile

from .spectrum_screen import HEIGHT, SCREEN_BYTES, WIDTH, decode_screen_pixels


class ZXScreenDecoder(ImageFile.PyDecoder):
    _pulls_fd = True

    def decode(self, buffer):
        data = self.fd.read(SCREEN_BYTES)
        self.set_as_raw(decode_screen_pixels(data))
        return -1, 0


class ZXScreenImageFile(ImageFile.ImageFile):
    format = "ZXSCR"
    format_description = "ZX Spectrum SCREEN$"

    def _open(self):
        self.fp.seek(0, 2)
        size = self.fp.tell()
        if size != SCREEN_BYTES:
            raise SyntaxError(f"not a ZX Spectrum SCREEN$ (size={size}, expected {SCREEN_BYTES})")
        self.fp.seek(0)
        self._mode = "RGB"
        self._size = (WIDTH, HEIGHT)
        self.info["pixel_aspect_ratio"] = (1, 1)
        self.tile = [("zxscr", (0, 0, WIDTH, HEIGHT), 0, None)]


def register() -> None:
    # No magic header; we rely on the .scr extension and the size check in
    # _open() to validate.
    Image.register_open(ZXScreenImageFile.format, ZXScreenImageFile)
    Image.register_extension(ZXScreenImageFile.format, ".scr")
    Image.register_decoder("zxscr", ZXScreenDecoder)
