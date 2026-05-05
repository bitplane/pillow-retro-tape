"""Pillow loaders for screens from 8-bit computer tapes."""

from . import (
    pillow_screen,
    spectrum_dsk,
    spectrum_scl,
    spectrum_scr,
    spectrum_slt,
    spectrum_sna,
    spectrum_szx,
    spectrum_tap,
    spectrum_trd,
    spectrum_tzx,
    spectrum_z80,
)

# The shared ScreenBytesDecoder is used by every multi-frame plugin.
pillow_screen.register_decoder()

# Pillow tries formats in registration order when several plugins accept
# the same prefix. Register strict-magic formats first, then loose
# fingerprints, then the no-magic formats from most specific (smallest
# size envelope) to least.
spectrum_dsk.register()  # "EXTENDED CPC DSK File" / "MV - CPC"
spectrum_tzx.register()  # "ZXTape!\x1a"
spectrum_szx.register()  # "ZXST"
spectrum_scl.register()  # "SINCLAIR"
spectrum_tap.register()  # length+flag fingerprint
spectrum_scr.register()  # exactly 6912 bytes
spectrum_sna.register()  # exactly 49179 or 131103 bytes
spectrum_trd.register()  # exactly 163840 / 327680 / 655360 bytes
spectrum_slt.register()  # z80 + "\x00\x00\x00SLT" marker
spectrum_z80.register()  # any v1/v2/v3 z80 (loosest)

__all__ = [
    "spectrum_dsk",
    "spectrum_scr",
    "spectrum_tap",
    "spectrum_tzx",
    "spectrum_z80",
]
