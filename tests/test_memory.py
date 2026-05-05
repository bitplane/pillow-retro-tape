import pytest

from pillow_retro_tape.blocks import (
    TYPE_CODE,
    TYPE_PROGRAM,
    Block,
)
from pillow_retro_tape.memory import SCREEN_ADDR, SCREEN_LEN, MemoryMap

from ._helpers import make_data_block, make_header_block, make_screen


def parse(raw: bytes) -> Block:
    return Block(flag=raw[0], payload=bytes(raw[1:-1]), checksum=raw[-1])


def test_apply_writes_code_block_at_declared_address():
    payload = b"\xaa\xbb\xcc\xdd"
    blocks = [
        parse(make_header_block(TYPE_CODE, "x", len(payload), 0x8000)),
        parse(make_data_block(payload)),
    ]
    mem = MemoryMap()
    mem.apply(blocks)
    assert bytes(mem.ram[0x8000:0x8004]) == payload
    # Surrounding RAM untouched.
    assert mem.ram[0x7FFF] == 0
    assert mem.ram[0x8004] == 0


def test_apply_ignores_non_code_blocks():
    payload = b"basic_program_bytes"
    blocks = [
        parse(make_header_block(TYPE_PROGRAM, "boot", len(payload), 5)),
        parse(make_data_block(payload)),
    ]
    mem = MemoryMap()
    mem.apply(blocks)
    assert all(b == 0 for b in mem.ram)
    assert mem.screens == []


def test_screen_written_to_4000_is_returned_first():
    screen = make_screen(pixel_byte=0xFF, attr_byte=0x07)
    blocks = [
        parse(make_header_block(TYPE_CODE, "scr", SCREEN_LEN, SCREEN_ADDR)),
        parse(make_data_block(screen)),
    ]
    mem = MemoryMap()
    mem.apply(blocks)
    assert mem.screen() == screen
    assert mem.screen_at() == screen


def test_data_block_without_preceding_header_is_skipped():
    blocks = [parse(make_data_block(b"orphan data"))]
    mem = MemoryMap()
    mem.apply(blocks)
    assert all(b == 0 for b in mem.ram)


def test_header_without_following_data_is_dropped():
    h = parse(make_header_block(TYPE_CODE, "x", 4, 0x8000))
    # Two headers in a row -> first one is forgotten when second arrives.
    h2 = parse(make_header_block(TYPE_CODE, "y", 4, 0xC000))
    payload = b"\x11\x22\x33\x44"
    blocks = [h, h2, parse(make_data_block(payload))]
    mem = MemoryMap()
    mem.apply(blocks)
    # Only the second header's address gets written.
    assert mem.ram[0x8000] == 0
    assert bytes(mem.ram[0xC000:0xC004]) == payload


def test_screen_falls_back_to_6912_byte_code_block_when_4000_empty():
    """Hobbit-style: header lies about address, but the 6912-byte block IS the screen."""
    screen = make_screen(pixel_byte=0xAA, attr_byte=0x07)
    blocks = [
        parse(make_header_block(TYPE_CODE, "p", SCREEN_LEN, 0x9C40)),
        parse(make_data_block(screen)),
    ]
    mem = MemoryMap()
    mem.apply(blocks)
    # $4000 is empty in the memory map -> fallback returns the collected screen.
    assert mem.screen_at() == bytes(SCREEN_LEN)
    assert mem.screen() == screen


def test_screen_raises_when_nothing_found():
    mem = MemoryMap()
    with pytest.raises(ValueError):
        mem.screen()


def test_truncated_payload_only_writes_declared_length():
    # Declared length 4 but data block carries 8 bytes — only 4 should land.
    payload = b"\x11\x22\x33\x44\xde\xad\xbe\xef"
    blocks = [
        parse(make_header_block(TYPE_CODE, "x", 4, 0x8000)),
        parse(make_data_block(payload)),
    ]
    mem = MemoryMap()
    mem.apply(blocks)
    assert bytes(mem.ram[0x8000:0x8004]) == b"\x11\x22\x33\x44"
    assert mem.ram[0x8004] == 0
