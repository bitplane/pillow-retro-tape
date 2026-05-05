"""64KB Spectrum memory map populated by walking a tape's block stream.

The model: walk header/data block pairs; for each CODE block, copy its payload
to the address declared in the preceding header. After the walk, the screen
typically lives at $4000-$5AFF.

Some tapes (e.g. The Hobbit) lie in the header — the BASIC loader uses
`LOAD "" CODE 16384` to override the load address. As a fallback we also
collect every 6912-byte CODE block we see and use the first one if $4000 is
empty.
"""

from typing import Iterable, Iterator

from .blocks import TYPE_CODE, Block, Header

RAM_SIZE = 0x10000
SCREEN_ADDR = 0x4000
SCREEN_LEN = 6912


class MemoryMap:
    def __init__(self) -> None:
        self.ram = bytearray(RAM_SIZE)
        self.screens: list[bytes] = []

    def apply(self, blocks: Iterable[Block]) -> None:
        pending: Header | None = None
        for block in blocks:
            if block.is_header():
                pending = Header.from_block(block)
                continue
            if block.is_data() and pending is not None:
                self._write(pending, block.payload)
            pending = None

    def _write(self, header: Header, payload: bytes) -> None:
        if header.type != TYPE_CODE:
            return
        data = payload[: header.length]
        addr = header.param1 & 0xFFFF
        end = min(addr + len(data), RAM_SIZE)
        self.ram[addr:end] = data[: end - addr]
        # Only collect as a screen candidate if we actually got the full
        # 6912 bytes (a truncated data block doesn't decode cleanly).
        if header.length == SCREEN_LEN and len(data) == SCREEN_LEN:
            self.screens.append(bytes(data))

    def screen_at(self, addr: int = SCREEN_ADDR) -> bytes:
        return bytes(self.ram[addr : addr + SCREEN_LEN])

    def screens_found(self) -> Iterator[bytes]:
        """Yield every plausible screen, in tape order.

        Yields each 6912-byte CODE block payload in the order it appeared
        on the tape (deduped). If the tape contained no 6912-byte CODE
        blocks at all, falls back to the data at $4000-$5AFF (catches
        custom loaders that wrote into screen memory via a non-standard
        block size).
        """
        seen: set[bytes] = set()
        for s in self.screens:
            if s not in seen:
                seen.add(s)
                yield s
        if not seen:
            primary = self.screen_at()
            if any(primary):
                yield primary

    def screen(self) -> bytes:
        for s in self.screens_found():
            return s
        raise ValueError("no screen found in memory map or 6912-byte CODE blocks")
