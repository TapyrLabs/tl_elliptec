"""Test doubles for exercising device logic without a real serial port."""
from __future__ import annotations

import pytest

from tl_elliptec import protocol
from tl_elliptec.bus import Reply
from tl_elliptec.exceptions import ElliptecStatusError, ElliptecTimeoutError
from tl_elliptec.status import StatusCode


class FakeBus:
    """Stands in for ElliptecBus: scripted replies keyed by (address, command)."""

    def __init__(self):
        self.scripted: dict[tuple[str, str], Reply] = {}
        self.sent: list[tuple[str, str, str]] = []
        #: priority passed to the most recent request()/send()/read_reply() call, for tests
        #: that need to check scheduling behavior without a real broker.
        self.priorities: list[int] = []
        self.urgent_sent: list[tuple[str, str, str]] = []

    def script(self, address: str, command: str, reply_command: str, data: str, reply_address: str = None) -> None:
        """Script a reply. ``reply_address`` lets a reply appear to come from a
        different address than the request (e.g. "ca" replying from the new
        address); defaults to the request's own address."""
        reply_addr = address if reply_address is None else reply_address
        raw = f"{reply_addr}{reply_command}{data}".encode("ascii")
        self.scripted[(address, command)] = Reply(reply_addr, reply_command, data, raw)

    def request(self, address, command, data="", expect=None, timeout=None,
                poll_timeout=None, raise_on_error=True, priority=0, reply_address=None):
        self.sent.append((address, command, data))
        self.priorities.append(priority)
        key = (address, command)
        if key not in self.scripted:
            raise ElliptecTimeoutError(f"no scripted reply for {key}")
        reply = self.scripted[key]
        if reply.command in ("GS", "BS") and raise_on_error:
            code = reply.as_status_code()
            if code != StatusCode.OK:
                raise ElliptecStatusError(reply.address, code)
        return reply

    def send(self, address, command, data="", priority=0):
        self.sent.append((address, command, data))

    def send_urgent(self, address, command, data=""):
        self.sent.append((address, command, data))
        self.urgent_sent.append((address, command, data))

    def read_reply(self, timeout=None, priority=0):
        raise ElliptecTimeoutError("no unsolicited reply queued")

    def scan(self, addresses=protocol.ADDRESS_CHARS, timeout=0.3):
        found = []
        for addr in addresses:
            try:
                self.request(addr, "in", expect="IN", timeout=timeout)
                found.append(addr)
            except ElliptecTimeoutError:
                continue
            except ElliptecStatusError:
                found.append(addr)
        return found


@pytest.fixture
def fake_bus():
    return FakeBus()
