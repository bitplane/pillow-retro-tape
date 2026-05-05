"""Pillow plugin for ZX Spectrum .sna snapshots.

The simplest snapshot format. Two flavours:

48K SNA (49179 bytes):
    [27]      register block (I, HL', DE', BC', AF', HL, DE, BC, IY, IX,
              IFF2, R, AF, SP, IM, border)
    [49152]   RAM at $4000-$FFFF, contiguous

128K SNA (131103 bytes):
    [27]      register block as above (SP points into 0xC000 area)
    [49152]   RAM showing the currently-paged 48K view (bank 5 at $4000,
              bank 2 at $8000, port-7FFD-selected bank at $C000)
    [2]       PC
    [1]       port 0x7FFD
    [1]       TR-DOS ROM paged flag
    [16384*5] the five RAM banks not in the currently-paged view

For screen extraction the data at $4000 is always the first 6912 bytes
after the 27-byte header in either flavour.
"""

from PIL import Image

from .pillow_screen import ScreenSequenceImageFile
from .snapshot import RAM_SIZE, MachineType, Snapshot

HEADER_LEN = 27
SNA_48K_SIZE = HEADER_LEN + 49152  # 49179
SNA_128K_SIZE = HEADER_LEN + 49152 + 4 + 16384 * 5  # 131103
VALID_SIZES = {SNA_48K_SIZE, SNA_128K_SIZE}


def parse_sna(data: bytes) -> Snapshot:
    if len(data) not in VALID_SIZES:
        raise ValueError(f"SNA file size {len(data)} not in {sorted(VALID_SIZES)}")
    border = data[26] & 0x07
    is_128k = len(data) == SNA_128K_SIZE
    snap = Snapshot(
        machine=MachineType.SPECTRUM_128K if is_128k else MachineType.SPECTRUM_48K,
        border=border,
    )
    snap.ram[0x4000:RAM_SIZE] = data[HEADER_LEN : HEADER_LEN + 49152]
    if is_128k:
        # Bank 5 (currently at $4000) and bank 2 (currently at $8000) are
        # canonical. The bank at $C000 depends on port 0x7FFD; we expose it
        # via .banks too so callers can inspect.
        port_7ffd = data[HEADER_LEN + 49152 + 2]
        snap.banks[5] = bytes(snap.ram[0x4000:0x8000])
        snap.banks[2] = bytes(snap.ram[0x8000:0xC000])
        snap.banks[port_7ffd & 0x07] = bytes(snap.ram[0xC000:RAM_SIZE])
        # Then the five extra banks. Banks present = {0..7} - {5, 2, port&7}.
        extra_offset = HEADER_LEN + 49152 + 4
        present = {5, 2, port_7ffd & 0x07}
        absent = [b for b in range(8) if b not in present]
        for i, bank in enumerate(absent):
            start = extra_offset + i * 16384
            snap.banks[bank] = bytes(data[start : start + 16384])
    return snap


def extract_screens(data: bytes) -> list[bytes]:
    snap = parse_sna(data)
    screens = [snap.screen()]
    shadow = snap.shadow_screen()
    if shadow is not None and shadow != screens[0]:
        screens.append(shadow)
    return screens


def extract_screen(data: bytes) -> bytes:
    return parse_sna(data).screen()


# --- Pillow plugin --------------------------------------------------------


class ZXSNAImageFile(ScreenSequenceImageFile):
    format = "ZXSNA"
    format_description = "ZX Spectrum SNA snapshot"

    def _open(self):
        self.fp.seek(0, 2)
        size = self.fp.tell()
        self.fp.seek(0)
        if size not in VALID_SIZES:
            raise SyntaxError(f"SNA size {size} not in {sorted(VALID_SIZES)}")
        data = self.fp.read()
        try:
            screens = extract_screens(data)
        except ValueError as e:
            raise SyntaxError(f"failed to parse SNA: {e}") from e
        self._set_frames(screens)


def _accept(prefix: bytes) -> bool:
    return len(prefix) >= 16


def register() -> None:
    Image.register_open(ZXSNAImageFile.format, ZXSNAImageFile, _accept)
    Image.register_extension(ZXSNAImageFile.format, ".sna")
