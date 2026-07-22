"""Tests for ElliptecBus.refresh_devices()/stream_positions() -- the live device
registry convenience layer, exercised by calling the unbound methods against
the FakeBus double (same pattern as the rest of the suite; it only needs
FakeBus to behave like a bus for request()/scan(), plus a _devices dict)."""
import itertools

from tl_elliptec import protocol
from tl_elliptec.bus import ElliptecBus
from tl_elliptec.devices.models import ELL14


def _info_data(ell_type_hex: str) -> str:
    return ell_type_hex + "00000001" + "2024" + "01" + "01" + "0168" + "00023000"


def test_refresh_devices_populates_registry_and_returns_json_safe_summary(fake_bus):
    fake_bus._devices = {}
    fake_bus.script("A", "in", "IN", _info_data("0E"))  # ELL14

    summary = ElliptecBus.refresh_devices(fake_bus, addresses="A")

    assert summary == {
        "A": {
            "ell_type": 14,
            "serial_number": "00000001",
            "travel": 360,
            "pulses_per_unit": fake_bus._devices["A"].pulses_per_unit,
        }
    }
    assert isinstance(fake_bus._devices["A"], ELL14)


def test_refresh_devices_mutates_registry_in_place(fake_bus):
    fake_bus._devices = {}
    fake_bus.script("A", "in", "IN", _info_data("0E"))
    ElliptecBus.refresh_devices(fake_bus, addresses="A")
    registry = fake_bus._devices  # keep a reference to the same dict object

    fake_bus.script("B", "in", "IN", _info_data("0E"))
    ElliptecBus.refresh_devices(fake_bus, addresses=protocol.ADDRESS_CHARS)

    assert fake_bus._devices is registry  # never rebound, just cleared+updated
    assert set(registry.keys()) == {"A", "B"}


def test_stream_positions_yields_only_changed_devices(fake_bus):
    fake_bus._devices = {}
    fake_bus.script("A", "in", "IN", _info_data("0E"))
    ElliptecBus.refresh_devices(fake_bus, addresses="A")

    positions = iter([0, 0, 5, 10])

    def fake_get_position_pulses(priority=0):
        return next(positions)

    fake_bus._devices["A"].get_position_pulses = fake_get_position_pulses

    gen = ElliptecBus.stream_positions(fake_bus, interval=0.001)
    ticks = list(itertools.islice(gen, 2))

    assert ticks == [
        {"A": {"pulses": 0, "units": 0 / fake_bus._devices["A"].pulses_per_unit}},
        {"A": {"pulses": 5, "units": 5 / fake_bus._devices["A"].pulses_per_unit}},
    ]
