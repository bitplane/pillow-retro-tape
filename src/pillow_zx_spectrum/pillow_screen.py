"""Shared Pillow plumbing for containers that may carry multiple SCREEN$.

A ZX Spectrum tape or disk can hold several 6912-byte SCREEN$ payloads —
multi-load games swap between them as the user progresses. We expose them
as Pillow frames so users can iterate the container with `seek()` /
`n_frames` / `PIL.ImageSequence.Iterator`.

Subclasses parse their container in `_open()`, then call `_set_frames()`
with the list of SCREEN$ candidates in container-natural order (tape
order for tapes, disk order for disks). Frame 0 is the default.
"""

import io

from PIL import ImageFile

from .spectrum_screen import HEIGHT, WIDTH, decode_screen_pixels

DECODER_NAME = "zxscreen-bytes"


class ScreenBytesDecoder(ImageFile.PyDecoder):
    """Decode a 6912-byte SCREEN$ blob (passed via `args[0]`) to RGB.

    `_pulls_fd = True` so Pillow skips its read-loop fallback (we don't
    consume any bytes from the fd; the data is in the decoder args).
    """

    _pulls_fd = True

    def decode(self, buffer):
        screen_bytes = self.args[0]
        self.set_as_raw(decode_screen_pixels(screen_bytes))
        return -1, 0


class ScreenSequenceImageFile(ImageFile.ImageFile):
    """Base for plugins that expose 1+ SCREEN$ frames."""

    def _set_frames(self, screens: list[bytes]) -> None:
        if not screens:
            raise SyntaxError("no SCREEN$ found in container")
        self._frames = screens
        self._n_frames = len(screens)
        self._current_frame = -1
        self._mode = "RGB"
        self._size = (WIDTH, HEIGHT)
        self.info["pixel_aspect_ratio"] = (1, 1)
        # Pillow's load() asserts self.fp is not None, then clears (and
        # often closes) it after the decode completes. The decoder doesn't
        # actually read from fp, so a fresh empty BytesIO per frame is
        # enough to satisfy the API.
        self._exclusive_fp = False
        self._switch_frame(0)

    def _switch_frame(self, frame: int) -> None:
        if frame == self._current_frame:
            return
        self._current_frame = frame
        self.tile = [(DECODER_NAME, (0, 0, WIDTH, HEIGHT), 0, (self._frames[frame],))]
        # Force re-decode via tile and provide a fresh placeholder fp.
        self.im = None
        self.fp = io.BytesIO(b"")

    def seek(self, frame: int) -> None:
        if not 0 <= frame < self._n_frames:
            raise EOFError(f"attempt to seek to frame {frame} (range 0..{self._n_frames - 1})")
        self._switch_frame(frame)

    def tell(self) -> int:
        return self._current_frame

    @property
    def n_frames(self) -> int:
        return self._n_frames


def register_decoder() -> None:
    from PIL import Image

    Image.register_decoder(DECODER_NAME, ScreenBytesDecoder)
