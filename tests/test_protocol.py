import pytest

from tl_elliptec import protocol


def test_encode_word_example_from_manual():
    # decimal 12345 (3039H) -> byte sequence 30,39
    assert protocol.encode_word(12345) == "3039"
    assert protocol.decode_word("3039") == 12345


def test_encode_short_negative_one():
    assert protocol.encode_short(-1) == "FFFF"
    assert protocol.decode_short("FFFF") == -1


def test_encode_dword_example_from_manual():
    # decimal 123456789 (75BCD15H) -> 07,5B,CD,15
    assert protocol.encode_dword(123456789) == "075BCD15"
    assert protocol.decode_dword("075BCD15") == 123456789


def test_encode_long_negative_one():
    assert protocol.encode_long(-1) == "FFFFFFFF"
    assert protocol.decode_long("FFFFFFFF") == -1


def test_encode_long_negative_example_from_manual():
    # decimal -123456789 -> F8,A4,32,EB
    assert protocol.encode_long(-123456789) == "F8A432EB"
    assert protocol.decode_long("F8A432EB") == -123456789


def test_build_message_move_absolute_example():
    # "Request a linear stage at address A to move at position 4mm" -> "Ama00002000"
    msg = protocol.build_message("A", "ma", protocol.encode_long(0x2000))
    assert msg == b"Ama00002000"


def test_build_message_change_address_example():
    msg = protocol.build_message("0", "ca", "A")
    assert msg == b"0caA"


def test_parse_message_position_reply():
    address, command, data = protocol.parse_message(b"APO00002000")
    assert (address, command, data) == ("A", "PO", "00002000")


def test_parse_message_status_reply():
    address, command, data = protocol.parse_message(b"0GS00")
    assert (address, command, data) == ("0", "GS", "00")


def test_invalid_address_rejected():
    with pytest.raises(ValueError):
        protocol.build_message("G", "in")


def test_out_of_range_raises():
    with pytest.raises(ValueError):
        protocol.encode_word(-1)
    with pytest.raises(ValueError):
        protocol.encode_word(70000)


def test_little_endian_helpers_for_current_curve():
    assert protocol.decode_le_word("BD00") == 0x00BD
    assert protocol.decode_le_dword("28040000") == 0x00000428
