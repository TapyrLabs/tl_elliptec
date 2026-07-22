"""Exceptions raised by the tl_elliptec library."""
from __future__ import annotations

from .status import StatusCode, describe


class ElliptecError(Exception):
    """Base class for all errors raised by this library."""


class ElliptecTimeoutError(ElliptecError):
    """No reply (or an incomplete reply) was received within the allotted time."""


class ElliptecProtocolError(ElliptecError):
    """A reply frame could not be parsed, or did not match what was expected."""


class ElliptecStatusError(ElliptecError):
    """The device replied with a GS/BS status frame indicating an error.

    Attributes:
        address: The address of the device that reported the error.
        code: The raw numeric status code (see :class:`~tl_elliptec.status.StatusCode`).
        status: ``code`` as a :class:`~tl_elliptec.status.StatusCode`, or
            ``None`` if it's outside the known/reserved range.
    """

    def __init__(self, address: str, code: int):
        """Args:
            address: The address of the device that reported the error.
            code: The raw numeric status code from the GS/BS reply.
        """
        self.address = address
        self.code = code
        try:
            self.status = StatusCode(code)
        except ValueError:
            self.status = None
        super().__init__(f"device {address}: status {code} ({describe(code)})")


class ElliptecUnsupportedError(ElliptecError):
    """The requested command is not supported by this device model."""
