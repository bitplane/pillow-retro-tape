"""Pillow loaders for screens from 8-bit computer tapes."""

from . import (
    pillow_screen,
    spectrum_dsk,
    spectrum_mgt,
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
# the same prefix. Register strict-magic formats first, then formats with
# strong in-_open validation (size constraints, system-sector magic),
# then the loose-accept ones last so they don't shadow the others.
spectrum_dsk.register()  # "EXTENDED CPC DSK File" / "MV - CPC"
spectrum_tzx.register()  # "ZXTape!\x1a"
spectrum_szx.register()  # "ZXST"
spectrum_scl.register()  # "SINCLAIR"
spectrum_scr.register()  # exactly 6912 bytes
spectrum_sna.register()  # exactly 49179 or 131103 bytes
spectrum_trd.register()  # TR-DOS magic byte 0x10 at $8E7
spectrum_mgt.register()  # MGT directory validity check
spectrum_slt.register()  # z80 + "\x00\x00\x00SLT" marker
spectrum_z80.register()  # any v1/v2/v3 z80 (loosest)
spectrum_tap.register()  # length+flag fingerprint (loosest tape)

__all__ = [
    "spectrum_dsk",
    "spectrum_scr",
    "spectrum_tap",
    "spectrum_tzx",
    "spectrum_z80",
]
