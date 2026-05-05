"""Common snapshot abstraction for ZX Spectrum memory images.

A snapshot is a frozen view of the Spectrum's RAM (and optionally CPU
registers) at a moment in time. Different on-disk formats (.z80, .sna, .szx)
all parse to a `Snapshot` so downstream code (the Pillow plugins, future
inspectors) can treat them uniformly.

For 48K snapshots, all RAM lives in `ram` ($0000-$FFFF, with $0000-$3FFF
being ROM and zeroed for snapshots). For 128K, `ram` holds the *currently
paged-in* memory image (bank 5 at $4000, bank 2 at $8000, the
port-0x7FFD-selected bank at $C000), and `banks` holds the eight 16K RAM
banks indexed by bank number 0..7. The screen always lives in bank 5,
which is also at $4000 in `ram`, so `screen()` works for both.
"""

from dataclasses import dataclass, field
from enum import Enum

from .spectrum_screen import SCREEN_BYTES

RAM_SIZE = 0x10000
SCREEN_ADDR = 0x4000


class MachineType(Enum):
    SPECTRUM_48K = "48k"
    SPECTRUM_128K = "128k"
    SPECTRUM_PLUS3 = "+3"
    PENTAGON = "pentagon"
    SAMRAM = "samram"
    UNKNOWN = "unknown"


@dataclass
class Snapshot:
    ram: bytearray = field(default_factory=lambda: bytearray(RAM_SIZE))
    banks: dict[int, bytes] = field(default_factory=dict)
    machine: MachineType = MachineType.UNKNOWN
    border: int = 0  # palette index 0..7

    def screen(self) -> bytes:
        """Return the 6912-byte main SCREEN$ at $4000-$5AFF."""
        return bytes(self.ram[SCREEN_ADDR : SCREEN_ADDR + SCREEN_BYTES])

    def shadow_screen(self) -> bytes | None:
        """Return the 128K shadow screen (bank 7 first 6912 bytes), if present."""
        b = self.banks.get(7)
        return b[:SCREEN_BYTES] if b else None
