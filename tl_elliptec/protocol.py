"""Low-level wire encoding for the Elliptec ELLx ASCII-hex protocol.

Every message is ASCII text: a 1-character device address, a 2-character
command mnemonic, and (for some commands) a variable-length hex-ASCII data
payload. Multi-byte values are big-endian ("Motorola format") *except* the
current-curve measurement payload (C1/C2), which the manual specifies as
little-endian.

See the manufacturer manual, sections 4-7, for the authoritative description.
"""
from __future__ import annotations

import struct

ADDRESS_CHARS = "0123456789ABCDEF"
LINE_TERMINATOR = b"\r\n"


def is_valid_address(address: str) -> bool:
    """Check whether a value is a valid single-hex-digit device address.

    Args:
        address: Candidate address, e.g. ``"0"`` or ``"F"``.

    Returns:
        ``True`` if ``address`` is a one-character string whose upper-cased
        value is one of ``0``-``9``/``A``-``F``, else ``False``.
    """
    return isinstance(address, str) and len(address) == 1 and address.upper() in ADDRESS_CHARS


def _check_int_range(value: int, nbits: int, signed: bool) -> None:
    if signed:
        lo, hi = -(1 << (nbits - 1)), (1 << (nbits - 1)) - 1
    else:
        lo, hi = 0, (1 << nbits) - 1
    if not (lo <= value <= hi):
        raise ValueError(f"value {value} out of range [{lo}, {hi}]")


def encode_int(value: int, nbytes: int, signed: bool = False) -> str:
    """Encode an integer as big-endian hex-ASCII.

    Args:
        value: The integer to encode.
        nbytes: Width of the encoded value, in bytes (the resulting string
            is ``2 * nbytes`` hex characters).
        signed: If ``True``, encode as 2's-complement; otherwise unsigned.

    Returns:
        Upper-case, zero-padded hex-ASCII string, e.g. ``"003039"`` for
        ``encode_int(12345, 3)``.

    Raises:
        ValueError: If ``value`` doesn't fit in ``nbytes`` bytes given
            ``signed``.
    """
    _check_int_range(value, nbytes * 8, signed)
    return value.to_bytes(nbytes, byteorder="big", signed=signed).hex().upper()


def decode_int(hexstr: str, signed: bool = False) -> int:
    """Decode a big-endian hex-ASCII string back to an integer.

    Args:
        hexstr: Hex-ASCII string, e.g. ``"3039"``.
        signed: If ``True``, interpret as 2's-complement; otherwise unsigned.

    Returns:
        The decoded integer.
    """
    raw = bytes.fromhex(hexstr)
    return int.from_bytes(raw, byteorder="big", signed=signed)


def encode_char(value: int) -> str:
    """Encode an unsigned 8-bit value (the protocol's "char" format).

    Args:
        value: Integer in range 0-255.

    Returns:
        2-character upper-case hex-ASCII string, e.g. ``"0A"`` for ``10``.
    """
    return encode_int(value, 1, signed=False)


def decode_char(hexstr: str) -> int:
    """Decode a 2-character hex-ASCII "char" value.

    Args:
        hexstr: 2-character hex-ASCII string, e.g. ``"0A"``.

    Returns:
        The decoded unsigned integer, e.g. ``10``.
    """
    return decode_int(hexstr, signed=False)


def encode_word(value: int) -> str:
    """Encode an unsigned 16-bit big-endian value (the protocol's "word" format).

    Args:
        value: Integer in range 0-65535.

    Returns:
        4-character upper-case hex-ASCII string, e.g. ``"3039"`` for ``12345``.
    """
    return encode_int(value, 2, signed=False)


def decode_word(hexstr: str) -> int:
    """Decode a 4-character hex-ASCII "word" value.

    Args:
        hexstr: 4-character hex-ASCII string, e.g. ``"3039"``.

    Returns:
        The decoded unsigned integer, e.g. ``12345``.
    """
    return decode_int(hexstr, signed=False)


def encode_short(value: int) -> str:
    """Encode a signed 16-bit big-endian value (the protocol's "short" format), 2's complement.

    Args:
        value: Integer in range -32768 to 32767.

    Returns:
        4-character upper-case hex-ASCII string, e.g. ``"FFFF"`` for ``-1``.
    """
    return encode_int(value, 2, signed=True)


def decode_short(hexstr: str) -> int:
    """Decode a 4-character hex-ASCII "short" value (signed, 2's complement).

    Args:
        hexstr: 4-character hex-ASCII string, e.g. ``"FFFF"``.

    Returns:
        The decoded signed integer, e.g. ``-1``.
    """
    return decode_int(hexstr, signed=True)


def encode_dword(value: int) -> str:
    """Encode an unsigned 32-bit big-endian value (the protocol's "dword" format).

    Args:
        value: Integer in range 0 to 2**32 - 1.

    Returns:
        8-character upper-case hex-ASCII string, e.g. ``"075BCD15"`` for
        ``123456789``.
    """
    return encode_int(value, 4, signed=False)


def decode_dword(hexstr: str) -> int:
    """Decode an 8-character hex-ASCII "dword" value.

    Args:
        hexstr: 8-character hex-ASCII string, e.g. ``"075BCD15"``.

    Returns:
        The decoded unsigned integer, e.g. ``123456789``.
    """
    return decode_int(hexstr, signed=False)


def encode_long(value: int) -> str:
    """Encode a signed 32-bit big-endian value (the protocol's "long" format), 2's complement.

    Used for position/offset fields (``ma``, ``mr``, ``go``/``so``, ``gj``/
    ``sj``, ``gp``/``PO``, ...).

    Args:
        value: Integer in range -2**31 to 2**31 - 1.

    Returns:
        8-character upper-case hex-ASCII string, e.g. ``"FFFFFFFF"`` for
        ``-1``.
    """
    return encode_int(value, 4, signed=True)


def decode_long(hexstr: str) -> int:
    """Decode an 8-character hex-ASCII "long" value (signed, 2's complement).

    Args:
        hexstr: 8-character hex-ASCII string, e.g. ``"FFFFFFFF"``.

    Returns:
        The decoded signed integer, e.g. ``-1``.
    """
    return decode_int(hexstr, signed=True)


def encode_float(value: float) -> str:
    """Encode a float as IEEE-754 single precision, big-endian.

    Args:
        value: The float to encode.

    Returns:
        8-character upper-case hex-ASCII string.
    """
    return struct.pack(">f", value).hex().upper()


def decode_float(hexstr: str) -> float:
    """Decode an 8-character hex-ASCII IEEE-754 single-precision float.

    Args:
        hexstr: 8-character hex-ASCII string.

    Returns:
        The decoded float.
    """
    return struct.unpack(">f", bytes.fromhex(hexstr))[0]


def encode_le_word(value: int) -> str:
    """Encode an unsigned 16-bit *little*-endian value.

    Only used for the current-curve measurement payload (``C1``/``C2``),
    which the manual specifies as little-endian unlike every other field.

    Args:
        value: Integer in range 0-65535.

    Returns:
        4-character upper-case hex-ASCII string.
    """
    return value.to_bytes(2, byteorder="little", signed=False).hex().upper()


def decode_le_word(hexstr: str) -> int:
    """Decode a 4-character hex-ASCII little-endian "word" value.

    Args:
        hexstr: 4-character hex-ASCII string.

    Returns:
        The decoded unsigned integer.
    """
    return int.from_bytes(bytes.fromhex(hexstr), byteorder="little", signed=False)


def decode_le_dword(hexstr: str) -> int:
    """Decode an 8-character hex-ASCII little-endian "dword" value.

    Args:
        hexstr: 8-character hex-ASCII string.

    Returns:
        The decoded unsigned integer.
    """
    return int.from_bytes(bytes.fromhex(hexstr), byteorder="little", signed=False)


def build_message(address: str, command: str, data: str = "") -> bytes:
    """Build a raw outgoing frame: ADDRESS + COMMAND + DATA (no terminator needed on TX).

    Args:
        address: Single hex-digit device address, e.g. ``"0"``.
        command: 2-character command mnemonic, e.g. ``"in"``.
        data: Optional hex-ASCII data payload.

    Returns:
        The ASCII-encoded frame bytes, e.g. ``b"0in"``.

    Raises:
        ValueError: If ``address`` isn't a valid single hex digit, or
            ``command`` isn't exactly 2 characters.
    """
    if not is_valid_address(address):
        raise ValueError(f"invalid address {address!r}, must be one hex digit 0-F")
    if len(command) != 2:
        raise ValueError(f"invalid command {command!r}, must be exactly 2 characters")
    return f"{address.upper()}{command}{data}".encode("ascii")


def parse_message(raw: bytes) -> tuple[str, str, str]:
    """Split a received frame (terminator already stripped) into (address, command, data).

    Args:
        raw: Raw frame bytes, e.g. ``b"0GS00"``.

    Returns:
        A ``(address, command, data)`` tuple, e.g. ``("0", "GS", "00")``.

    Raises:
        ValueError: If ``raw`` decodes to fewer than 3 characters.
    """
    text = raw.decode("ascii", errors="replace").strip()
    if len(text) < 3:
        raise ValueError(f"malformed frame, too short: {text!r}")
    address, command, data = text[0], text[1:3], text[3:]
    return address, command, data
