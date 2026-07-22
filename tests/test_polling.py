"""Tests for ElliptecDevice.poll_position and friends."""
import itertools
import threading
import time

from tl_elliptec import protocol
from tl_elliptec.bus import Reply, RequestPriority
from tl_elliptec.devices.models import ELL6
from tl_elliptec.exceptions import ElliptecTimeoutError


class SequenceBus:
    """Returns successive scripted "gp" positions, one per call (clamped at the end)."""

    def __init__(self, pulses_sequence):
        self._sequence = list(pulses_sequence)
        self._index = 0

    def request(self, address, command, data="", expect=None, timeout=None,
                poll_timeout=None, raise_on_error=True, priority=0):
        if command != "gp":
            raise ElliptecTimeoutError(f"unscripted command {command!r}")
        pulses = self._sequence[min(self._index, len(self._sequence) - 1)]
        self._index += 1
        return Reply(address, "PO", protocol.encode_long(pulses), b"")

    def send(self, *args, **kwargs):
        raise NotImplementedError

    def read_reply(self, *args, **kwargs):
        raise ElliptecTimeoutError("no unsolicited reply queued")


def test_poll_position_only_yields_on_change():
    bus = SequenceBus([0, 0, 5, 5, 5, 10])
    device = ELL6(bus, "0")  # DEFAULT_PULSES_PER_UNIT = 1.0, so units == pulses here

    values = list(itertools.islice(device.poll_position(interval=0.001), 3))

    assert values == [0.0, 5.0, 10.0]


def test_poll_position_respects_tolerance():
    bus = SequenceBus([0, 1, 2, 3, 10])
    device = ELL6(bus, "0")

    values = list(itertools.islice(device.poll_position(interval=0.001, tolerance=2), 2))

    assert values == [0.0, 3.0]


def test_poll_position_stops_when_stop_event_is_set():
    bus = SequenceBus(list(range(1000)))  # never runs out, so only stop_event can end the loop
    device = ELL6(bus, "0")
    stop = threading.Event()

    def stop_soon():
        time.sleep(0.03)
        stop.set()

    threading.Thread(target=stop_soon).start()
    values = list(device.poll_position(interval=0.005, stop_event=stop))

    assert 0 < len(values) < 1000


def test_poll_position_pulses_variant_tracks_raw_positions():
    bus = SequenceBus([0, 4])
    device = ELL6(bus, "0")
    assert list(itertools.islice(device.poll_position_pulses(interval=0.001), 2)) == [0, 4]


def test_poll_position_range_without_calibration_never_yields():
    # ELL6 never got a live "in" reply here, so pulses_per_full_range is
    # unknown; get_position_range() raises internally, which poll_position_range
    # swallows as a transient error (retried next tick) rather than propagating.
    bus = SequenceBus([0, 4])
    device = ELL6(bus, "0")
    stop = threading.Event()

    def stop_soon():
        time.sleep(0.02)
        stop.set()

    threading.Thread(target=stop_soon).start()
    values = list(device.poll_position_range(interval=0.001, stop_event=stop))

    assert values == []


def test_poll_position_issues_requests_at_poll_priority(fake_bus):
    fake_bus.script("0", "gp", "PO", protocol.encode_long(0))
    device = ELL6(fake_bus, "0")

    next(device.poll_position(interval=0.001))

    assert fake_bus.priorities[-1] == RequestPriority.POLL
