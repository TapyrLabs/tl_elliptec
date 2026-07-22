from tl_elliptec import protocol
from tl_elliptec.devices.base import DeviceInfo, ElliptecDevice, MotorInfo
from tl_elliptec.devices.models import ELL6, ELL14
from tl_elliptec.status import StatusCode


def test_get_info_matches_manual_worked_example(fake_bus):
    # RX "0, IN, 06,12345678,2015,01,81,001F,00000001"
    data = "06" + "12345678" + "2015" + "01" + "81" + "001F" + "00000001"
    fake_bus.script("0", "in", "IN", data)

    device = ELL6(fake_bus, "0")
    info = device.get_info()

    assert info.ell_type == 6
    assert info.serial_number == "12345678"
    assert info.year == "2015"
    assert info.firmware_release == "01"
    assert info.is_imperial is True
    assert info.hardware_release == 1
    assert info.travel == 31
    assert info.pulses_per_unit == 1


def test_info_and_serial_number_are_cached_from_construction(fake_bus):
    # get_info() is called automatically during __init__ (for calibration);
    # .info/.serial_number should expose that cached result without a
    # second "in" round trip.
    data = "06" + "12345678" + "2015" + "01" + "81" + "001F" + "00000001"
    fake_bus.script("0", "in", "IN", data)

    device = ELL6(fake_bus, "0")
    request_count_before = len(fake_bus.sent)

    assert device.info is not None
    assert device.info.serial_number == "12345678"
    assert device.serial_number == "12345678"
    assert len(fake_bus.sent) == request_count_before  # no extra request made


def test_info_and_serial_number_are_none_without_a_reachable_device(fake_bus):
    device = ELL6(fake_bus, "0")  # no "in" scripted, calibration failed silently

    assert device.info is None
    assert device.serial_number is None


def test_get_motor_info_matches_manual_worked_example(fake_bus):
    # RX "0I1100428FFFFFFFF00BD008B"
    fake_bus.script("0", "i1", "I1", "100428FFFFFFFF00BD008B")

    device = ELL6(fake_bus, "0")
    motor = device.get_motor_info(1)

    assert motor.loop_on is True
    assert motor.motor_on is False
    assert round(motor.current_amps, 2) == 0.57  # manual: "0.57A"
    assert motor.forward_period == 0x00BD
    assert motor.backward_period == 0x008B


def test_get_status_ok(fake_bus):
    fake_bus.script("0", "gs", "GS", "00")
    device = ELL6(fake_bus, "0")
    assert device.get_status() == StatusCode.OK


def test_change_address_updates_local_state(fake_bus):
    # Real hardware replies to "ca" from the *new* address, not the one the
    # command was sent to -- script that explicitly rather than letting the
    # test double default to the (unrealistic) same-address echo.
    fake_bus.script("0", "ca", "GS", "00", reply_address="A")
    device = ELL6(fake_bus, "0")
    device.change_address("A")
    assert device.address == "A"


def test_ell6_has_no_motor2(fake_bus):
    from tl_elliptec.exceptions import ElliptecUnsupportedError
    import pytest

    device = ELL6(fake_bus, "0")
    with pytest.raises(ElliptecUnsupportedError):
        device.get_motor_info(2)


def test_move_absolute_pulses_matches_manual_worked_example(fake_bus):
    # TX "Ama00002000" -> RX "APO00002000"
    fake_bus.script("A", "ma", "PO", "00002000")
    device = ELL14(fake_bus, "A")

    position = device.move_absolute_pulses(0x2000)

    assert position == 0x2000
    assert fake_bus.sent[-1] == ("A", "ma", "00002000")


def test_move_absolute_converts_units_using_default_pulses_per_unit(fake_bus):
    # No "in" scripted, so calibration falls back to ELL14.DEFAULT_PULSES_PER_UNIT (398 pulses/deg).
    fake_bus.script("A", "ma", "PO", protocol.encode_long(10 * 398))
    device = ELL14(fake_bus, "A")

    assert device.pulses_per_unit == 398.0
    position = device.move_absolute(10)  # 10 degrees

    assert position == 10.0
    assert fake_bus.sent[-1] == ("A", "ma", protocol.encode_long(3980))


def test_rotary_pulses_field_is_per_revolution_not_per_degree(fake_bus):
    # Empirically, ELL14's "in" reply reports pulses for one full 360 deg
    # revolution (e.g. 143360), not pulses/degree (398) as the field name
    # implies. get_position()/move_absolute() must divide by travel (360)
    # to recover real pulses/degree, or a move of "10 degrees" would
    # actually land the stage at 10/143360 of a revolution (~0.025 deg).
    info_data = "0E" + "00000001" + "2024" + "01" + "01" + "0168" + "00023000"  # "0E" = hex(14) = ELL14  # travel=360, pulses/rev=143360
    fake_bus.script("A", "in", "IN", info_data)
    fake_bus.script("A", "ma", "PO", protocol.encode_long(round(2 * 398.222)))

    device = ELL14(fake_bus, "A")

    assert device.pulses_per_full_range == 143360
    assert round(device.pulses_per_unit, 1) == 398.2  # 143360 / 360

    position = device.move_absolute(2)  # 2 degrees, not 2/143360 of a revolution

    assert round(position, 2) == 2.0
    assert fake_bus.sent[-1] == ("A", "ma", protocol.encode_long(round(2 * 398.222)))


def test_move_absolute_range_uses_raw_full_travel_pulse_count(fake_bus):
    info_data = "0E" + "00000001" + "2024" + "01" + "01" + "0168" + "00023000"  # "0E" = hex(14) = ELL14  # pulses/rev=143360
    fake_bus.script("A", "in", "IN", info_data)
    fake_bus.script("A", "ma", "PO", protocol.encode_long(143360 // 2))

    device = ELL14(fake_bus, "A")
    position = device.move_absolute_range(0.5)  # halfway across full travel

    assert position == 0.5
    assert fake_bus.sent[-1] == ("A", "ma", protocol.encode_long(143360 // 2))


def test_pulses_per_full_range_requires_calibration(fake_bus):
    from tl_elliptec.exceptions import ElliptecError
    import pytest

    device = ELL14(fake_bus, "A")  # no "in" scripted, calibration failed silently
    with pytest.raises(ElliptecError):
        device.pulses_per_full_range


def test_get_home_offset_pulses_matches_manual_worked_example(fake_bus):
    fake_bus.script("A", "go", "HO", "00000200")
    device = ELL14(fake_bus, "A")
    assert device.get_home_offset_pulses() == 0x200
    assert device.get_home_offset() == 0x200 / device.pulses_per_unit


def test_get_velocity_matches_manual_worked_example(fake_bus):
    fake_bus.script("A", "gv", "GV", "64")
    device = ELL14(fake_bus, "A")
    assert device.get_velocity() == 100


def test_scan_current_curve_sample_count(fake_bus):
    sample = "BD00" + "28040000"  # little-endian period + current, matches earlier examples
    data = sample * 87
    fake_bus.script("A", "c1", "C1", data)
    device = ELL14(fake_bus, "A")

    samples = device.scan_current_curve(1)

    assert len(samples) == 87
    assert samples[0].period == 0x00BD
    assert round(samples[0].current_amps, 2) == 0.57


def test_constructing_from_a_bus_instance_does_not_own_it(fake_bus):
    device = ELL14(fake_bus, "A")
    assert device._owns_bus is False
    device.close()
    # FakeBus has no close(); if the device had wrongly tried to close a
    # shared bus this would have raised AttributeError above.


def test_constructing_from_a_port_string_owns_and_closes_its_own_bus(monkeypatch):
    created = {}

    class FakeSerialBus:
        def __init__(self, port, timeout=None, **kwargs):
            created["port"] = port
            created["timeout"] = timeout
            self.closed = False

        def request(self, address, command, data="", **kwargs):
            from tl_elliptec.exceptions import ElliptecTimeoutError

            raise ElliptecTimeoutError("no device wired up in this test")

        def close(self):
            self.closed = True

    monkeypatch.setattr("tl_elliptec.devices.base.ElliptecBus", FakeSerialBus)

    device = ELL14("COM5", "A")

    assert created["port"] == "COM5"
    assert device._owns_bus is True
    assert isinstance(device.bus, FakeSerialBus)

    with device:
        pass
    assert device.bus.closed is True


def test_stop_uses_send_urgent_not_a_queued_request(fake_bus):
    # stop() must bypass the request broker (see ElliptecBus.send_urgent),
    # since its whole purpose is interrupting a command that's already
    # occupying the queue -- a normal request() would just queue behind it.
    device = ELL14(fake_bus, "A")

    result = device.stop()

    assert result is None
    assert fake_bus.urgent_sent == [("A", "st", "")]
