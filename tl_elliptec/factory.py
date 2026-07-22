"""Auto-detection and instantiation of the right device class for each unit on a bus."""
from __future__ import annotations

import time
from typing import Callable, Optional

from . import protocol
from .bus import ElliptecBus
from .devices.base import DeviceInfo, ElliptecDevice
from .devices.models import ELL6, ELL6B, MODEL_REGISTRY
from .exceptions import ElliptecError, ElliptecStatusError, ElliptecTimeoutError


def create_device(bus: ElliptecBus, address: str, timeout: Optional[float] = None) -> ElliptecDevice:
    """Query the device at ``address`` and instantiate the matching model class.

    Raises :class:`ElliptecError` if the device doesn't answer or reports an
    unrecognized ELL type.
    """
    reply = bus.request(address, "in", expect="IN", timeout=timeout)
    info = DeviceInfo.from_reply(reply)
    cls = MODEL_REGISTRY.get(info.ell_type)
    if cls is None:
        raise ElliptecError(
            f"device at address {address} reports unknown ELL type {info.ell_type!r}"
        )
    if cls is ELL6:
        # ELL6 (1 motor) and ELL6B (2 motors) share the same reported type;
        # tell them apart by whether motor 2 responds at all.
        try:
            bus.request(address, "i2", expect="I2", timeout=timeout or 0.5)
            cls = ELL6B
        except (ElliptecTimeoutError, ElliptecStatusError):
            cls = ELL6
    # cls(...) re-queries "in" itself (to populate pulses_per_unit calibration);
    # the extra round trip keeps device construction uniform for direct callers too.
    return cls(bus, address, timeout=timeout)


def discover_devices(
    bus: ElliptecBus,
    addresses: str = protocol.ADDRESS_CHARS,
    timeout: float = 0.3,
) -> dict[str, ElliptecDevice]:
    """Scan ``addresses`` (default: all 16) and return ``{address: device}`` for each that answers."""
    devices: dict[str, ElliptecDevice] = {}
    for addr in addresses:
        try:
            devices[addr] = create_device(bus, addr, timeout=timeout)
        except (ElliptecTimeoutError, ElliptecError):
            continue
    return devices


def _default_wait_for_next_device(index: int, total: int) -> None:
    input(
        f"Connect device {index + 1} of {total} now -- it must be the only one "
        f"currently sitting at address '0' -- then press Enter..."
    )


def setup_devices(
    bus: ElliptecBus,
    count: int,
    start_address: str = "1",
    wait_for_next_device: Optional[Callable[[int, int], None]] = None,
    detect_timeout: float = 60.0,
    poll_interval: float = 0.5,
) -> list[str]:
    """Assign unique addresses to ``count`` factory-default (address "0") devices, one at a time.

    Every ELLx module ships at address "0". Two or more of them on the same
    bus simultaneously both answer to "0" and their replies collide
    electrically -- neither ``scan()`` nor ``discover_devices()`` can see
    anything in that state, and there's no way to tell them apart in
    software once that's already happened. This walks you through the
    one-time fix: address them one at a time.

    For each of ``count`` devices, this:

    1. Calls ``wait_for_next_device(index, count)`` -- by default, prints an
       instruction and blocks on ``input()`` -- so you can physically connect
       (or power up) the next *unaddressed* device now. Devices already
       given a unique, non-zero address in an earlier step (or before this
       call) can stay connected; only ever have one device at "0" at a time.
    2. Polls address "0" until something answers (or ``detect_timeout``
       elapses, raising :class:`ElliptecError`).
    3. Assigns it the next address starting at ``start_address``, skipping
       any address already occupied on the bus (detected via ``bus.scan()``
       up front, so devices already addressed in a previous run aren't
       reused).
    4. Confirms it now answers at the new address and saves it (``us``,
       non-volatile -- this is a one-time step per device, not a per-session
       one).

    Returns the newly assigned addresses, in order. If two devices are
    *already* colliding at "0" when you call this, disconnect down to one of
    them first -- this function has no way to un-collide them for you.
    """
    if not protocol.is_valid_address(start_address):
        raise ValueError(f"invalid start_address {start_address!r}")
    if wait_for_next_device is None:
        wait_for_next_device = _default_wait_for_next_device

    occupied = {addr for addr in bus.scan(timeout=poll_interval) if addr != "0"}
    order = protocol.ADDRESS_CHARS
    cursor = order.index(start_address.upper())

    assigned: list[str] = []
    for i in range(count):
        wait_for_next_device(i, count)

        deadline = time.monotonic() + detect_timeout
        while True:
            try:
                bus.request("0", "in", expect="IN", timeout=poll_interval)
                break
            except ElliptecStatusError:
                break  # answered, just with a non-OK status -- still "present"
            except ElliptecTimeoutError:
                if time.monotonic() >= deadline:
                    raise ElliptecError(
                        f"no device appeared at address '0' within {detect_timeout}s "
                        f"(device {i + 1} of {count})"
                    ) from None

        while cursor < len(order) and order[cursor] in occupied:
            cursor += 1
        if cursor >= len(order):
            raise ElliptecError("no free addresses left (0-F are all in use)")
        new_address = order[cursor]
        cursor += 1

        bus.request("0", "ca", new_address, expect="GS", reply_address=new_address)
        try:
            bus.request(new_address, "us", expect="GS")
        except ElliptecStatusError:
            pass  # best-effort; the address change itself already succeeded

        occupied.add(new_address)
        assigned.append(new_address)

    return assigned
