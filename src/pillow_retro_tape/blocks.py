"""ZX Spectrum tape block representation.

A "standard ROM loader block" is the unit the Spectrum tape ROM reads:
1 flag byte + N payload bytes + 1 checksum byte (XOR of flag and payload).

TAP files store these directly; TZX 0x10/0x11 blocks contain the same shape.

Header blocks (flag=0x00, payload length=17) describe the next data block:
type, name, length, and two type-dependent parameters (load address etc.).
"""

from dataclasses import dataclass

MIN_BLOCK_LEN = 2  # 1 flag byte + 1 checksum byte (zero-byte payload allowed)

HEADER_FLAG = 0x00
DATA_FLAG = 0xFF
HEADER_PAYLOAD_LEN = 17

TYPE_PROGRAM = 0
TYPE_NUMBER_ARRAY = 1
TYPE_CHAR_ARRAY = 2
TYPE_CODE = 3  # also SCREEN$, which is just a 6912-byte CODE block at $4000


@dataclass(frozen=True)
class Block:
    flag: int
    payload: bytes
    checksum: int

    def is_header(self) -> bool:
        return self.flag == HEADER_FLAG and len(self.payload) == HEADER_PAYLOAD_LEN

    def is_data(self) -> bool:
        return self.flag == DATA_FLAG

    def checksum_valid(self) -> bool:
        c = self.flag
        for b in self.payload:
            c ^= b
        return c == self.checksum


@dataclass(frozen=True)
class Header:
    type: int
    name: str  # 10 chars, ASCII, trailing spaces stripped
    length: int  # declared length of the next data block's payload
    param1: int  # CODE: load address; PROGRAM: autostart line
    param2: int  # CODE: unused; PROGRAM: variable area offset

    @classmethod
    def from_block(cls, block: "Block") -> "Header":
        if not block.is_header():
            raise ValueError("not a header block")
        p = block.payload
        return cls(
            type=p[0],
            name=p[1:11].decode("ascii", errors="replace").rstrip(),
            length=int.from_bytes(p[11:13], "little"),
            param1=int.from_bytes(p[13:15], "little"),
            param2=int.from_bytes(p[15:17], "little"),
        )


def parse_block(raw: bytes) -> Block:
    """Parse a standard ROM-format block: flag + payload + checksum."""
    if len(raw) < MIN_BLOCK_LEN:
        raise ValueError(f"block too short: {len(raw)} bytes (min {MIN_BLOCK_LEN})")
    return Block(flag=raw[0], payload=bytes(raw[1:-1]), checksum=raw[-1])
