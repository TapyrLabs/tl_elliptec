"""Tests for create_device/discover_devices, especially the hex-vs-decimal ELL-type gotcha."""
from tl_elliptec.devices.models import ELL6, ELL9, ELL12, ELL14, ELL20, MODEL_REGISTRY
from tl_elliptec.exceptions import ElliptecError
from tl_elliptec.factory import create_device, discover_devices, setup_devices

import pytest


def _info_data(ell_type_hex: str) -> str:
    # ELL(2) SN(8) YEAR(4) FW(2) HW(2) TRAVEL(4) PULSES(8), arbitrary but well-formed.
    return ell_type_hex + "00000001" + "2024" + "01" + "01" + "0168" + "00023000"


def test_ell14_reports_hex_encoded_type_not_decimal(fake_bus):
    # Regression test: the "ELL type" field is hex-ASCII, e.g. ELL14 (decimal
    # 14) reports "0E" (0x0E), not the literal digits "14". "14" is actually
    # ELL20's hex code (0x14 == 20). Getting this wrong made create_device()
    # silently fail to recognize a real ELL14 on the bus.
    fake_bus.script("A", "in", "IN", _info_data("0E"))

    device = create_device(fake_bus, "A")

    assert isinstance(device, ELL14)


def test_ell20_reports_0x14_not_ell14(fake_bus):
    fake_bus.script("A", "in", "IN", _info_data("14"))

    device = create_device(fake_bus, "A")

    assert isinstance(device, ELL20)


def test_model_registry_is_keyed_by_plain_decimal_model_number():
    # MODEL_REGISTRY itself should never store or compare hex strings -- the
    # hex-ASCII <-> decimal conversion happens once, at the wire boundary in
    # DeviceInfo.from_reply, via protocol.decode_char.
    assert MODEL_REGISTRY[6] is ELL6
    assert MODEL_REGISTRY[9] is ELL9
    assert MODEL_REGISTRY[12] is ELL12
    assert MODEL_REGISTRY[14] is ELL14
    assert all(isinstance(key, int) for key in MODEL_REGISTRY)


def test_unrecognized_ell_type_raises_instead_of_silently_matching(fake_bus):
    fake_bus.script("A", "in", "IN", _info_data("FF"))

    with pytest.raises(ElliptecError):
        create_device(fake_bus, "A")


def test_discover_devices_finds_a_real_ell14(fake_bus):
    # This is exactly the scenario reported: a single ELL14 on the bus,
    # findable via bus.scan() (which ignores ell_type) but previously
    # invisible to discover_devices() because create_device() raised on the
    # unrecognized-at-the-time "0E" type, and discover_devices()'s
    # `except (ElliptecTimeoutError, ElliptecError)` silently swallowed it.
    fake_bus.script("A", "in", "IN", _info_data("0E"))

    devices = discover_devices(fake_bus, addresses="A")

    assert "A" in devices
    assert isinstance(devices["A"], ELL14)


def _no_wait(index, total):
    pass  # stand-in for the interactive input() prompt in tests


def test_setup_devices_assigns_the_next_free_address(fake_bus):
    fake_bus.script("0", "in", "IN", _info_data("0E"))  # the new device, still at "0"
    fake_bus.script("0", "ca", "GS", "00", reply_address="1")
    fake_bus.script("1", "us", "GS", "00")

    calls = []
    assigned = setup_devices(fake_bus, count=1, wait_for_next_device=lambda i, t: calls.append((i, t)))

    assert assigned == ["1"]
    assert calls == [(0, 1)]
    assert ("0", "ca", "1") in fake_bus.sent


def test_setup_devices_skips_addresses_already_occupied(fake_bus):
    # Address "1" is already taken by a previously-addressed device.
    fake_bus.script("1", "in", "IN", _info_data("09"))
    fake_bus.script("0", "in", "IN", _info_data("0E"))  # the new device, still at "0"
    fake_bus.script("0", "ca", "GS", "00", reply_address="2")
    fake_bus.script("2", "us", "GS", "00")

    assigned = setup_devices(fake_bus, count=1, wait_for_next_device=_no_wait)

    assert assigned == ["2"]


def test_setup_devices_addresses_several_in_sequence(fake_bus):
    fake_bus.script("0", "in", "IN", _info_data("0E"))
    fake_bus.script("0", "ca", "GS", "00", reply_address="1")
    fake_bus.script("1", "us", "GS", "00")
    fake_bus.script("2", "us", "GS", "00")

    calls = []

    def wait(i, t):
        calls.append((i, t))
        if i == 1:
            # Simulate the first device no longer being at "0" (it moved to
            # "1"); the second one just arrived there instead.
            fake_bus.script("0", "ca", "GS", "00", reply_address="2")

    assigned = setup_devices(fake_bus, count=2, wait_for_next_device=wait)

    assert assigned == ["1", "2"]
    assert calls == [(0, 2), (1, 2)]


def test_setup_devices_raises_if_no_device_appears(fake_bus):
    with pytest.raises(ElliptecError):
        setup_devices(
            fake_bus, count=1, wait_for_next_device=_no_wait, detect_timeout=0.02, poll_interval=0.005
        )


def test_setup_devices_raises_when_addresses_are_exhausted(fake_bus):
    fake_bus.script("0", "in", "IN", _info_data("0E"))
    fake_bus.script("0", "ca", "GS", "00", reply_address="F")
    fake_bus.script("F", "us", "GS", "00")

    with pytest.raises(ElliptecError):
        # start_address "F" is the last available address, so a second
        # device has nowhere to go.
        setup_devices(fake_bus, count=2, start_address="F", wait_for_next_device=_no_wait)
