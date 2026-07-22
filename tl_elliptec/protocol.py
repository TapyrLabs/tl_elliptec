"""Low-level wire encoding for the Elliptec ELLx ASCII-hex protocol.

Every message is ASCII text: a 1-character device address, a 2-character
command mnemonic, and (for some commands) a variable-length hex-ASCII data
payload. Multi-byte values are big-endian ("Motorola format") *except* the
current-curve measurement payload (C1/C2), which the manual specifies as
little-endian.

See "etn032283-d03.pdf", sections 4-7, for the authoritative description.
"""
from __future__ import annotations

import struct

ADDRESS_CHARS = "0123456789ABCDEF"
LINE_TERMINATOR = b"\r\n"


def is_valid_address(address: str) -> bool:
    return isinstance(address, str) and len(address) == 1 and address.upper() in ADDRESS_CHARS


def _check_int_range(value: int, nbits: int, signed: bool) -> None:
    if signed:
        lo, hi = -(1 << (nbits - 1)), (1 << (nbits - 1)) - 1
    else:
        lo, hi = 0, (1 << nbits) - 1
    if not (lo <= value <= hi):
        raise ValueError(f"value {value} out of range [{lo}, {hi}]")


def encode_int(value: int, nbytes: int, signed: bool = False) -> str:
    """Encode an integer as big-endian hex-ASCII, upper case, zero padded."""
    _check_int_range(value, nbytes * 8, signed)
    return value.to_bytes(nbytes, byteorder="big", signed=signed).hex().upper()


def decode_int(hexstr: str, signed: bool = False) -> int:
    raw = bytes.fromhex(hexstr)
    return int.from_bytes(raw, byteorder="big", signed=signed)


def encode_char(value: int) -> str:
    return encode_int(value, 1, signed=False)


def decode_char(hexstr: str) -> int:
    return decode_int(hexstr, signed=False)


def encode_word(value: int) -> str:
    """Unsigned 16-bit big-endian."""
    return encode_int(value, 2, signed=False)


def decode_word(hexstr: str) -> int:
    return decode_int(hexstr, signed=False)


def encode_short(value: int) -> str:
    """Signed 16-bit big-endian, 2's complement."""
    return encode_int(value, 2, signed=True)


def decode_short(hexstr: str) -> int:
    return decode_int(hexstr, signed=True)


def encode_dword(value: int) -> str:
    """Unsigned 32-bit big-endian."""
    return encode_int(value, 4, signed=False)


def decode_dword(hexstr: str) -> int:
    return decode_int(hexstr, signed=False)


def encode_long(value: int) -> str:
    """Signed 32-bit big-endian, 2's complement. Used for positions/offsets."""
    return encode_int(value, 4, signed=True)


def decode_long(hexstr: str) -> int:
    return decode_int(hexstr, signed=True)


def encode_float(value: float) -> str:
    """IEEE-754 single precision, big-endian."""
    return struct.pack(">f", value).hex().upper()


def decode_float(hexstr: str) -> float:
    return struct.unpack(">f", bytes.fromhex(hexstr))[0]


def encode_le_word(value: int) -> str:
    return value.to_bytes(2, byteorder="little", signed=False).hex().upper()


def decode_le_word(hexstr: str) -> int:
    return int.from_bytes(bytes.fromhex(hexstr), byteorder="little", signed=False)


def decode_le_dword(hexstr: str) -> int:
    return int.from_bytes(bytes.fromhex(hexstr), byteorder="little", signed=False)


def build_message(address: str, command: str, data: str = "") -> bytes:
    """Build a raw outgoing frame: ADDRESS + COMMAND + DATA (no terminator needed on TX)."""
    if not is_valid_address(address):
        raise ValueError(f"invalid address {address!r}, must be one hex digit 0-F")
    if len(command) != 2:
        raise ValueError(f"invalid command {command!r}, must be exactly 2 characters")
    return f"{address.upper()}{command}{data}".encode("ascii")


def parse_message(raw: bytes) -> tuple[str, str, str]:
    """Split a received frame (terminator already stripped) into (address, command, data)."""
    text = raw.decode("ascii", errors="replace").strip()
    if len(text) < 3:
        raise ValueError(f"malformed frame, too short: {text!r}")
    address, command, data = text[0], text[1:3], text[3:]
    return address, command, data
