"""Common abstraction for ZX Spectrum / Amstrad disk images.

A `DiskImage` is just a list of `Sector` records plus geometry metadata.
Each format-specific parser (e.g. CPC DSK, TR-DOS .trd) reads its own
container and produces a `DiskImage`. Downstream code uses
`logical_sectors()` (sorted by track / side / sector ID) and `flat()` to
reach into a file system.
"""

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class Sector:
    track: int
    side: int
    sector_id: int  # the FDC "R" field; on +3 disks this is 1..9
    data: bytes


@dataclass
class DiskImage:
    tracks: int = 0
    sides: int = 0
    sectors: list[Sector] = field(default_factory=list)

    def logical_sectors(self) -> Iterable[Sector]:
        return sorted(self.sectors, key=lambda s: (s.track, s.side, s.sector_id))

    def flat(self) -> bytes:
        return b"".join(s.data for s in self.logical_sectors())
