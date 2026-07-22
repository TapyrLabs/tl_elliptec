"""ElliptecBus tests that exercise real reply-matching logic (not the FakeBus double,
which always echoes replies from the same address it was asked)."""
import threading

import pytest

import tl_elliptec.bus as busmod
from tl_elliptec.exceptions import ElliptecTimeoutError


class FakeSerial:
    """Minimal stand-in for pyserial's Serial: pre-loaded read buffer, captures writes."""

    def __init__(self, to_read: bytes = b""):
        self._buf = bytearray(to_read)
        self.timeout = None
        self.written = bytearray()
        self.is_open = True

    def write(self, data: bytes) -> None:
        self.written += data

    def flush(self) -> None:
        pass

    def read(self, n: int = 1) -> bytes:
        if not self._buf:
            return b""
        chunk = bytes(self._buf[:n])
        del self._buf[:n]
        return chunk

    def close(self) -> None:
        self.is_open = False


@pytest.fixture
def fake_serial_bus(monkeypatch):
    """Returns (bus_factory, fake_serial) -- call bus_factory() after setting
    fake_serial's read buffer to build an ElliptecBus backed by it."""
    holder = {}

    def fake_serial_ctor(port, **kwargs):
        return holder["serial"]

    monkeypatch.setattr(busmod.serial, "Serial", fake_serial_ctor)

    def make(to_read: bytes, timeout: float = 0.3) -> busmod.ElliptecBus:
        holder["serial"] = FakeSerial(to_read)
        return busmod.ElliptecBus("FAKE", timeout=timeout)

    return make


def test_change_address_reply_is_matched_against_the_new_address(fake_serial_bus):
    # A real device replies to "0ca1" with "1GS00" -- from the NEW address.
    bus = fake_serial_bus(b"1GS00\r\n")
    try:
        reply = bus.request("0", "ca", "1", expect="GS", reply_address="1", timeout=0.3)
        assert reply.address == "1"
        assert reply.command == "GS"
    finally:
        bus.close()


def test_reply_from_new_address_is_ignored_without_the_override(fake_serial_bus):
    # Without reply_address, the bus (correctly) only accepts replies from
    # the address it wrote to -- this documents why change_address() must
    # pass reply_address explicitly, and guards against regressing that fix.
    bus = fake_serial_bus(b"1GS00\r\n")
    try:
        with pytest.raises(ElliptecTimeoutError):
            bus.request("0", "ca", "1", expect="GS", timeout=0.3)
    finally:
        bus.close()


def test_send_urgent_bypasses_the_broker_queue(fake_serial_bus):
    # A "st" sent while a move is already occupying the worker thread must
    # reach the wire immediately -- not queue behind the in-flight job like
    # a normal request()/send() call would.
    bus = fake_serial_bus(b"")  # send_urgent doesn't read a reply
    try:
        blocker_started = threading.Event()
        release = threading.Event()

        def slow_job():
            blocker_started.set()
            assert release.wait(timeout=2), "test setup: release was never set"
            return "done"

        future = bus._broker.submit(0, slow_job)
        assert blocker_started.wait(timeout=2), "worker never started the blocking job"

        bus.send_urgent("1", "st")

        assert bytes(bus._serial.written) == b"1st\r\n"

        release.set()
        assert future.result(timeout=2) == "done"
    finally:
        bus.close()
