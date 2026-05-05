import pytest

from pillow_retro_tape.blocks import (
    DATA_FLAG,
    HEADER_FLAG,
    TYPE_CODE,
    TYPE_PROGRAM,
    Block,
    Header,
)

from ._helpers import make_data_block, make_header_block


def parse_block(raw: bytes) -> Block:
    return Block(flag=raw[0], payload=bytes(raw[1:-1]), checksum=raw[-1])


def test_data_block_classification():
    raw = make_data_block(b"hello", flag=DATA_FLAG)
    b = parse_block(raw)
    assert b.is_data()
    assert not b.is_header()
    assert b.checksum_valid()


def test_header_block_classification():
    raw = make_header_block(TYPE_CODE, "screen", 6912, 0x4000)
    b = parse_block(raw)
    assert b.is_header()
    assert not b.is_data()
    assert b.checksum_valid()


def test_header_block_payload_must_be_17_bytes():
    # Flag=0x00 but wrong payload length -> not a header.
    raw = make_data_block(b"\x00" * 10, flag=0x00)
    b = parse_block(raw)
    assert not b.is_header()


def test_checksum_invalid_when_corrupted():
    raw = bytearray(make_data_block(b"abc"))
    raw[-1] ^= 1
    b = parse_block(bytes(raw))
    assert not b.checksum_valid()


def test_header_from_block_for_code():
    raw = make_header_block(TYPE_CODE, "loader", 6912, 0x4000, 0x8000)
    h = Header.from_block(parse_block(raw))
    assert h.type == TYPE_CODE
    assert h.name == "loader"
    assert h.length == 6912
    assert h.param1 == 0x4000
    assert h.param2 == 0x8000


def test_header_from_block_for_program():
    raw = make_header_block(TYPE_PROGRAM, "boot", 191, 5, 0x00BF)
    h = Header.from_block(parse_block(raw))
    assert h.type == TYPE_PROGRAM
    assert h.name == "boot"
    assert h.length == 191
    assert h.param1 == 5  # autostart line


def test_header_from_block_rejects_data_block():
    raw = make_data_block(b"x" * 17, flag=DATA_FLAG)
    with pytest.raises(ValueError):
        Header.from_block(parse_block(raw))


def test_header_name_strips_trailing_spaces():
    raw = make_header_block(TYPE_CODE, "p", 6912, 0x4000)
    h = Header.from_block(parse_block(raw))
    assert h.name == "p"


def test_flag_constants():
    assert HEADER_FLAG == 0x00
    assert DATA_FLAG == 0xFF
