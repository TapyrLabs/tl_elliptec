"""Base device class and capability mixins for ELLx modules.

``ElliptecDevice`` implements every command that is common to *all* ELLx
modules (identification, status, saving parameters, addressing, per-motor
tuning, isolation). Commands that only some device families support are
implemented as mixins (``MotionMixin``, ``AutoHomingMixin``,
``OptimizeCleanMixin``, ``ZeroPositionMixin``, ``ResetFactoryMixin``) and are
composed onto the concrete model classes in ``tl_elliptec.devices.models``
according to what section 3 ("applicability") of each command in the manual
states.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Iterator, Optional, Union

from .. import protocol
from ..bus import ElliptecBus, Reply, RequestPriority
from ..exceptions import ElliptecError, ElliptecUnsupportedError
from ..status import StatusCode


@dataclass
class DeviceInfo:
    address: str
    ell_type: int           # decimal model number, e.g. 14 for an ELL14 (see note below)
    serial_number: str
    year: str
    firmware_release: str
    hardware_release: int
    is_imperial: bool
    travel: int             # mm or degrees, per the model table
    pulses_per_unit: int

    @classmethod
    def from_reply(cls, reply: Reply) -> "DeviceInfo":
        # Data layout (hex-ASCII chars): ELL(2) SN(8) YEAR(4) FW(2) HW(2) TRAVEL(4) PULSES(8)
        #
        # Every multi-hex-digit field here is hex-ASCII per the protocol's
        # general encoding rule (manual section 4: "HEX ASCII DATA... i.e.,
        # '0A' means decimal value 10"). ell_type is no exception: an ELL14
        # reports "0E" (0x0E == 14 decimal), not the literal digits "14" --
        # that only coincidentally looked right for single-digit models like
        # the ELL6 ("06"). Decode it to a real int here, once, at the wire
        # boundary, so nothing downstream (MODEL_REGISTRY, user code, ...)
        # ever has to think in hex again.
        data = reply.data
        ell_type = protocol.decode_char(data[0:2])
        serial_number = data[2:10]
        year = data[10:14]
        firmware_release = data[14:16]
        hw_byte = protocol.decode_char(data[16:18])
        is_imperial = bool(hw_byte & 0x80)
        hardware_release = hw_byte & 0x7F
        travel = protocol.decode_word(data[18:22])
        pulses_per_unit = protocol.decode_dword(data[22:30])
        return cls(
            address=reply.address,
            ell_type=ell_type,
            serial_number=serial_number,
            year=year,
            firmware_release=firmware_release,
            hardware_release=hardware_release,
            is_imperial=is_imperial,
            travel=travel,
            pulses_per_unit=pulses_per_unit,
        )


@dataclass
class MotorInfo:
    loop_on: bool
    motor_on: bool
    current_amps: float
    forward_period: int
    backward_period: int

    @property
    def forward_frequency_hz(self) -> Optional[float]:
        if self.forward_period in (0, 0xFFFF):
            return None
        return 14740000 / self.forward_period

    @property
    def backward_frequency_hz(self) -> Optional[float]:
        if self.backward_period in (0, 0xFFFF):
            return None
        return 14740000 / self.backward_period

    @classmethod
    def from_reply(cls, reply: Reply) -> "MotorInfo":
        # Per the worked example in the manual ("0I1100428FFFFFFFF00BD008B" ->
        # Loop=1, Motor=0, Current=0428, rampUp=FFFF, rampDown=FFFF, FwP=00BD,
        # BwP=008B), Loop/Motor are single hex *nibbles*, not the usual 2-digit
        # "char" byte encoding used elsewhere in the protocol.
        data = reply.data
        loop_on = data[0:1] != "0"
        motor_on = data[1:2] != "0"
        current_raw = protocol.decode_word(data[2:6])
        forward_period = protocol.decode_word(data[14:18])
        backward_period = protocol.decode_word(data[18:22])
        return cls(
            loop_on=loop_on,
            motor_on=motor_on,
            current_amps=current_raw / 1866.0,
            forward_period=forward_period,
            backward_period=backward_period,
        )


@dataclass
class CurrentCurveSample:
    period: int
    current_amps: float

    @property
    def frequency_hz(self) -> float:
        return 14740000 / self.period if self.period else float("inf")


def period_for_frequency(frequency_hz: float) -> int:
    """Convert a target resonant frequency (Hz) to the protocol's "period" units."""
    return round(14740000 / frequency_hz)


def _encode_tuned_period(period: int) -> str:
    """FwP/BwP set commands require the most-significant nibble forced to 0x8."""
    if not (0 <= period <= 0x0FFF):
        raise ValueError(f"period {period} out of range for a 12-bit tuned value")
    return f"{0x8000 | period:04X}"


RESTORE_FACTORY_PERIOD = "FFF"


class ElliptecDevice:
    """Commands common to every ELLx module.

    Can be constructed two ways:

    * Point-to-point (one controller wired straight to one device)::

        stage = ELL14("COM5")               # owns and opens the serial port itself

    * Shared multidrop bus (a hub with several addressed devices)::

        bus = ElliptecBus("COM5")
        stage = ELL14(bus, address="2")     # bus is shared, not owned/closed by the device
        slider = ELL9(bus, address="3")
    """

    #: Overridden by subclasses. Some families lack a second motor (ELL6),
    #: and ELL16/ELL21/ELL22 do not support tunable forward/backward periods
    #: or the hardware-button spontaneous status messages.
    has_motor2: bool = True
    supports_motor_tuning: bool = True
    supports_button_messages: bool = True

    #: Fallback encoder-pulses-per-unit (per mm or per degree) used by
    #: unit-based position methods (move_absolute, get_position, ...) when
    #: live calibration from get_info() isn't available. 1 is a safe
    #: identity default for devices with no natural physical unit (e.g.
    #: indexed multi-position sliders); motion-capable subclasses override
    #: this with the pulses/mm or pulses/degree value from the model table
    #: in the manual. This is always the *corrected* per-unit value, i.e.
    #: after the PULSES_FIELD_IS_PER_REVOLUTION adjustment below has already
    #: been applied conceptually.
    DEFAULT_PULSES_PER_UNIT: float = 1.0

    #: On rotary stages (ELL14/16/18/21/22), the "PULSES/M.U." field
    #: reported by get_info() is empirically the encoder count for one full
    #: revolution (e.g. 143360 for the ELL14), *not* pulses-per-degree as
    #: the field name suggests -- dividing raw position by it directly
    #: yields a 0..1 fraction of the full travel, not degrees. The true
    #: pulses-per-degree is that field divided by the reported travel (e.g.
    #: 143360 / 360 = 398.2, matching the manual's documented "398
    #: pulse/deg"). Linear stages (ELL17/ELL20) and the slider/iris families
    #: do not show this: their reported field already is pulses/mm or
    #: pulses/position, so this stays False for them.
    PULSES_FIELD_IS_PER_REVOLUTION: bool = False

    def __init__(
        self,
        port_or_bus: Union[str, ElliptecBus],
        address: str = "0",
        timeout: Optional[float] = None,
        **bus_kwargs,
    ):
        if not protocol.is_valid_address(address):
            raise ValueError(f"invalid address {address!r}")
        if isinstance(port_or_bus, str):
            self.bus = ElliptecBus(port_or_bus, timeout=timeout or 2.0, **bus_kwargs)
            self._owns_bus = True
        else:
            if bus_kwargs:
                raise TypeError("bus_kwargs are only valid when constructing from a port string")
            self.bus = port_or_bus
            self._owns_bus = False
        self.address = address.upper()
        self.timeout = timeout
        self._info: Optional[DeviceInfo] = None
        #: Exactly what get_info() reported in its PULSES/M.U. field, with no
        #: correction applied. This is the denominator for the "_range"
        #: methods (0..1 across the device's full travel).
        self._raw_pulses_per_unit: Optional[int] = None
        #: The corrected pulses-per-degree or pulses-per-mm value used by the
        #: plain unit methods (move_absolute, get_position, ...).
        self._pulses_per_unit: Optional[float] = None
        try:
            self.refresh_calibration()
        except ElliptecError:
            # No device answered yet (e.g. not wired up, still booting, or
            # this is a point-to-point construction before the port is
            # ready). Fall back to DEFAULT_PULSES_PER_UNIT; call
            # refresh_calibration() explicitly later once the device is up.
            pass

    def __repr__(self) -> str:
        if self._info is not None:
            return f"{type(self).__name__}(address={self.address!r}, serial_number={self._info.serial_number!r})"
        return f"{type(self).__name__}(address={self.address!r})"

    def close(self) -> None:
        """Close the underlying serial port, but only if this device opened it itself."""
        if self._owns_bus:
            self.bus.close()

    def __enter__(self) -> "ElliptecDevice":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _request(self, command: str, data: str = "", **kwargs) -> Reply:
        kwargs.setdefault("timeout", self.timeout)
        return self.bus.request(self.address, command, data, **kwargs)

    def _require(self, supported: bool, feature: str) -> None:
        if not supported:
            raise ElliptecUnsupportedError(
                f"{type(self).__name__} at address {self.address} does not support {feature}"
            )

    # -- cached identification info ---------------------------------------

    @property
    def info(self) -> Optional[DeviceInfo]:
        """The DeviceInfo from the last successful get_info()/refresh_calibration() call.

        Populated automatically at construction time (see ``__init__``), so
        it's normally already available -- e.g. right after
        ``discover_devices()`` -- without an extra round trip. ``None`` if
        the device has never successfully answered an "in" request (e.g.
        constructed before it was wired up; call ``refresh_calibration()``
        once it's reachable).
        """
        return self._info

    @property
    def serial_number(self) -> Optional[str]:
        """Shortcut for ``info.serial_number``; ``None`` if ``info`` isn't available yet."""
        return self._info.serial_number if self._info is not None else None

    # -- physical-unit <-> encoder-pulse conversion ----------------------

    def refresh_calibration(self) -> DeviceInfo:
        """Query the device and cache its pulses-per-unit and full-range pulse counts."""
        info = self.get_info()
        self._info = info
        self._raw_pulses_per_unit = info.pulses_per_unit
        if self.PULSES_FIELD_IS_PER_REVOLUTION and info.travel:
            self._pulses_per_unit = info.pulses_per_unit / info.travel
        else:
            self._pulses_per_unit = info.pulses_per_unit
        return info

    @property
    def pulses_per_unit(self) -> float:
        """Encoder pulses per mm/degree, from live calibration if available, else the model default."""
        if self._pulses_per_unit:
            return self._pulses_per_unit
        return self.DEFAULT_PULSES_PER_UNIT

    @property
    def pulses_per_full_range(self) -> int:
        """Raw PULSES/M.U. value from get_info(): encoder pulses across the device's whole travel.

        This is the denominator used by the "_range" methods (e.g.
        ``get_position_range``), which report position as a 0..1 fraction of
        full travel instead of physical units. Unlike ``pulses_per_unit``,
        there's no static per-model fallback for this -- call
        ``refresh_calibration()`` once the device is reachable.
        """
        if self._raw_pulses_per_unit is None:
            raise ElliptecError(
                f"{type(self).__name__} at address {self.address}: full-range pulse calibration "
                "unknown; call refresh_calibration() once the device is reachable"
            )
        return self._raw_pulses_per_unit

    def _to_unit(self, pulses: Optional[int]) -> Optional[float]:
        return None if pulses is None else pulses / self.pulses_per_unit

    def _to_pulses(self, value: float) -> int:
        return round(value * self.pulses_per_unit)

    def _to_range(self, pulses: Optional[int]) -> Optional[float]:
        return None if pulses is None else pulses / self.pulses_per_full_range

    def _from_range(self, fraction: float) -> int:
        return round(fraction * self.pulses_per_full_range)

    # -- identification & status ----------------------------------------

    def get_info(self) -> DeviceInfo:
        """HOSTREQ_INFORMATION "in" / DEVGET_INFORMATION "IN"."""
        reply = self._request("in", expect="IN")
        return DeviceInfo.from_reply(reply)

    def get_status(self) -> StatusCode:
        """HOSTREQ_STATUS "gs" / DEVGET_STATUS "GS". Reading the status clears it."""
        reply = self._request("gs", expect="GS", raise_on_error=False)
        return StatusCode(reply.as_status_code())

    def save_user_data(self) -> None:
        """HOSTREQ_SAVE_USER_DATA "us". Persists tuned motor/user parameters to EEPROM."""
        self._request("us")

    def change_address(self, new_address: str) -> None:
        """HOSTREQ_CHANGEADDRESS "ca". Device replies from the *new* address."""
        if not protocol.is_valid_address(new_address):
            raise ValueError(f"invalid address {new_address!r}")
        new_address = new_address.upper()
        self.bus.request(self.address, "ca", new_address, expect="GS", reply_address=new_address)
        self.address = new_address

    def isolate_minutes(self, minutes: int) -> None:
        """HOST_ISOLATEMINUTES "is". Device will not reply for this many minutes."""
        self._request("is", protocol.encode_char(minutes))

    def group_address(self, temporary_address: str) -> None:
        """HOST_GROUPADDRESS "ga". Device listens on ``temporary_address`` until its next move."""
        if not protocol.is_valid_address(temporary_address):
            raise ValueError(f"invalid address {temporary_address!r}")
        self._request("ga", temporary_address.upper())

    def skip_frequency_search(self) -> None:
        """HOSTREQ_SKIP_FREQUENCY "sk". Skips the startup frequency scan; needs EEPROM reset to undo."""
        self.bus.request(self.address, "sk", expect="GS")

    # -- per-motor info / tuning ------------------------------------------

    def get_motor_info(self, motor: int) -> MotorInfo:
        """HOSTREQ_MOTORxINFO "i1"/"i2"."""
        self._check_motor(motor)
        reply = self._request(f"i{motor}", expect=f"I{motor}")
        return MotorInfo.from_reply(reply)

    def set_forward_period(self, motor: int, period: Optional[int]) -> None:
        """HOSTSET_FWP_MOTORx "f1"/"f2". Pass ``None`` to restore the factory default."""
        self._check_motor(motor)
        self._require(self.supports_motor_tuning, "forward/backward period tuning")
        data = RESTORE_FACTORY_PERIOD if period is None else _encode_tuned_period(period)
        self._request(f"f{motor}", data)

    def set_forward_frequency(self, motor: int, frequency_hz: float) -> None:
        self.set_forward_period(motor, period_for_frequency(frequency_hz))

    def set_backward_period(self, motor: int, period: Optional[int]) -> None:
        """HOSTSET_BWP_MOTORx "b1"/"b2". Pass ``None`` to restore the factory default."""
        self._check_motor(motor)
        self._require(self.supports_motor_tuning, "forward/backward period tuning")
        data = RESTORE_FACTORY_PERIOD if period is None else _encode_tuned_period(period)
        self._request(f"b{motor}", data)

    def set_backward_frequency(self, motor: int, frequency_hz: float) -> None:
        self.set_backward_period(motor, period_for_frequency(frequency_hz))

    def search_frequency(self, motor: int, timeout: float = 30.0) -> StatusCode:
        """HOSTREQ_SEARCHFREQ_MOTORx "s1"/"s2". The moving part may move. Remember to `save_user_data()`."""
        self._check_motor(motor)
        reply = self.bus.request(self.address, f"s{motor}", expect="GS", timeout=timeout)
        return StatusCode(reply.as_status_code())

    def scan_current_curve(self, motor: int, timeout: float = 15.0) -> list[CurrentCurveSample]:
        """HOSTREQ_SCANCURRENTCURVE_MOTORx "c1"/"c2" + DEVGET_CURRENTCURVEMEASURE "C1"/"C2".

        Takes up to ~12 seconds on the device. Returns 87 (period, current) samples
        spanning ~70-120 kHz.
        """
        self._check_motor(motor)
        reply = self.bus.request(
            self.address, f"c{motor}", expect=f"C{motor}", timeout=timeout
        )
        samples = []
        data = reply.data
        for i in range(87):
            offset = i * 12
            chunk = data[offset : offset + 12]
            if len(chunk) < 12:
                break
            period = protocol.decode_le_word(chunk[0:4])
            current_raw = protocol.decode_le_dword(chunk[4:12])
            samples.append(CurrentCurveSample(period=period, current_amps=current_raw / 1866.0))
        return samples

    def _check_motor(self, motor: int) -> None:
        if motor not in (1, 2):
            raise ValueError("motor must be 1 or 2")
        if motor == 2:
            self._require(self.has_motor2, "a second motor")

    # -- position (universal per the manual's individual command notes) --
    #
    # The "plain-named" methods (get_position, forward, backward, ...) work
    # in physical units (mm or degrees), converted using pulses_per_unit.
    # The "_pulses" methods are the raw wire values, for callers that want
    # to bypass unit conversion entirely.

    def get_position_pulses(self, priority: int = RequestPriority.COMMAND) -> int:
        """HOST_GETPOSITION "gp" / DEV_GETPOSITION "PO". Raw encoder pulses, signed.

        ``priority`` is forwarded to the bus's request broker (see
        :class:`~tl_elliptec.bus.RequestPriority`); leave it at the default
        unless this call is opportunistic background polling that shouldn't
        delay other, explicitly issued commands (see ``poll_position``).
        """
        reply = self._request("gp", expect="PO", priority=priority)
        return protocol.decode_long(reply.data)

    def get_position(self, priority: int = RequestPriority.COMMAND) -> float:
        """Current position in mm or degrees (see ``pulses_per_unit``)."""
        return self._to_unit(self.get_position_pulses(priority=priority))

    def get_position_range(self, priority: int = RequestPriority.COMMAND) -> float:
        """Current position as a 0..1 fraction of the device's full travel."""
        return self._to_range(self.get_position_pulses(priority=priority))

    def forward_pulses(self, timeout: float = 30.0) -> Optional[int]:
        """HOST_FORWARD "fw". Moves by the configured jog step (or continuously, see ``MotionMixin``)."""
        reply = self.bus.request(self.address, "fw", timeout=timeout)
        return self._position_from_move_reply(reply)

    def forward(self, timeout: float = 30.0) -> Optional[float]:
        """Jog forward by the configured step size. Returns the resulting position in units."""
        return self._to_unit(self.forward_pulses(timeout=timeout))

    def backward_pulses(self, timeout: float = 30.0) -> Optional[int]:
        """HOST_BACKWARD "bw"."""
        reply = self.bus.request(self.address, "bw", timeout=timeout)
        return self._position_from_move_reply(reply)

    def backward(self, timeout: float = 30.0) -> Optional[float]:
        """Jog backward by the configured step size. Returns the resulting position in units."""
        return self._to_unit(self.backward_pulses(timeout=timeout))

    @staticmethod
    def _position_from_move_reply(reply: Reply) -> int:
        if reply.command == "PO":
            return protocol.decode_long(reply.data)
        # Terminal "GS00" with no position payload (e.g. continuous-motion units).
        return None

    def get_button_status(self) -> Optional[Reply]:
        """Poll once, without blocking indefinitely, for a spontaneous BS/BO message.

        Returns ``None`` if nothing has arrived within a short timeout. These
        messages are pushed by the device when its physical FWD/BWD/JOG
        buttons are used; they are not solicited by a host command.
        """
        self._require(self.supports_button_messages, "hardware button status messages")
        try:
            return self.bus.read_reply(timeout=0.05)
        except Exception:
            return None

    # -- position polling -------------------------------------------------
    #
    # These are generators, not background threads: each one only does work
    # (sleep + poll) while something is actively iterating it. That's what
    # makes them safe to run from a *dedicated* thread per device on a
    # shared bus -- e.g. `threading.Thread(target=lambda: list(dev.poll_position()))`
    # for each of several devices -- without needing any locking of your
    # own: every poll request goes through the same ElliptecBus request
    # broker as everything else, at RequestPriority.POLL, so it always
    # yields the wire to explicitly issued commands (moves, reads, ...)
    # that are actively waiting for their turn, no matter how often the
    # pollers fire.

    def _poll(
        self,
        getter: Callable[[], Optional[float]],
        interval: float,
        tolerance: float,
        stop_event: Optional[threading.Event],
    ) -> Iterator[float]:
        last: Optional[float] = None
        while stop_event is None or not stop_event.is_set():
            try:
                current = getter()
            except ElliptecError:
                current = None
            else:
                if current is not None and (last is None or abs(current - last) > tolerance):
                    last = current
                    yield current
            if stop_event is not None:
                if stop_event.wait(interval):
                    break
            else:
                time.sleep(interval)

    def poll_position(
        self,
        interval: float = 0.15,
        tolerance: float = 0.0,
        stop_event: Optional[threading.Event] = None,
    ) -> Iterator[float]:
        """Yield the position (mm/degrees), polling roughly every ``interval`` seconds.

        Only yields when the position has changed by more than ``tolerance``
        since the last yielded value (default 0: yield on any change).
        Transient read errors (e.g. a busy status) are swallowed and simply
        retried on the next tick rather than raised.

        Polling requests are issued at ``RequestPriority.POLL`` (see
        ``tl_elliptec.bus.RequestPriority``), so they never delay explicitly
        issued commands sharing the same bus, including ones for other
        devices on a multidrop hub.

        Pass ``stop_event`` (a ``threading.Event``) to stop the loop cleanly
        from another thread -- handy when this generator is being driven by
        a dedicated polling thread, e.g.::

            stop = threading.Event()
            t = threading.Thread(target=lambda: [on_position(p) for p in stage.poll_position(stop_event=stop)])
            t.start()
            ...
            stop.set()
            t.join()

        Without ``stop_event``, stop iteration the normal way (``break`` out
        of a ``for`` loop consuming it, or call ``.close()`` on the
        generator from the same thread that's driving it).
        """
        yield from self._poll(
            lambda: self.get_position(priority=RequestPriority.POLL), interval, tolerance, stop_event
        )

    def poll_position_pulses(
        self,
        interval: float = 0.15,
        tolerance: float = 0.0,
        stop_event: Optional[threading.Event] = None,
    ) -> Iterator[int]:
        """Like ``poll_position``, but yields raw encoder pulses."""
        yield from self._poll(
            lambda: self.get_position_pulses(priority=RequestPriority.POLL), interval, tolerance, stop_event
        )

    def poll_position_range(
        self,
        interval: float = 0.15,
        tolerance: float = 0.0,
        stop_event: Optional[threading.Event] = None,
    ) -> Iterator[float]:
        """Like ``poll_position``, but yields a 0..1 fraction of the device's full travel."""
        yield from self._poll(
            lambda: self.get_position_range(priority=RequestPriority.POLL), interval, tolerance, stop_event
        )


class MotionMixin:
    """ho, ma, mr, home-offset, jog-step-size, velocity: not on multi-position sliders.

    As with the base class's position methods, the plain-named methods here
    (``home``, ``move_absolute``, ``move_relative``, ``get_home_offset``,
    ``set_home_offset``, ``get_jog_step_size``, ``set_jog_step_size``) work
    in physical units (mm or degrees); ``_pulses``-suffixed twins work in
    raw encoder pulses, and ``_range``-suffixed twins (on ``home``,
    ``move_absolute``, ``move_relative``) work in a 0..1 fraction of the
    device's full travel.
    """

    def home_pulses(self, direction: int = 0, timeout: float = 30.0) -> Optional[int]:
        """HOSTREQ_HOME "ho". ``direction``: 0 = clockwise, 1 = counter-clockwise (rotary only)."""
        reply = self.bus.request(
            self.address, "ho", protocol.encode_char(direction), timeout=timeout
        )
        return self._position_from_move_reply(reply)

    def home(self, direction: int = 0, timeout: float = 30.0) -> Optional[float]:
        """Move to the home position. Returns the resulting position in units."""
        return self._to_unit(self.home_pulses(direction, timeout=timeout))

    def home_range(self, direction: int = 0, timeout: float = 30.0) -> Optional[float]:
        """Move to the home position. Returns the resulting position as a 0..1 fraction of full travel."""
        return self._to_range(self.home_pulses(direction, timeout=timeout))

    def move_absolute_pulses(self, position: int, timeout: float = 30.0) -> Optional[int]:
        """HOSTREQ_MOVEABSOLUTE "ma". ``position`` in raw encoder pulses."""
        reply = self.bus.request(
            self.address, "ma", protocol.encode_long(position), timeout=timeout
        )
        return self._position_from_move_reply(reply)

    def move_absolute(self, position: float, timeout: float = 30.0) -> Optional[float]:
        """Move to an absolute position in mm or degrees (see ``pulses_per_unit``)."""
        return self._to_unit(self.move_absolute_pulses(self._to_pulses(position), timeout=timeout))

    def move_absolute_range(self, fraction: float, timeout: float = 30.0) -> Optional[float]:
        """Move to an absolute position given as a 0..1 fraction of the device's full travel."""
        return self._to_range(self.move_absolute_pulses(self._from_range(fraction), timeout=timeout))

    def move_relative_pulses(self, delta: int, timeout: float = 30.0) -> Optional[int]:
        """HOSTREQ_MOVERELATIVE "mr". ``delta`` in raw encoder pulses, signed."""
        reply = self.bus.request(
            self.address, "mr", protocol.encode_long(delta), timeout=timeout
        )
        return self._position_from_move_reply(reply)

    def move_relative(self, delta: float, timeout: float = 30.0) -> Optional[float]:
        """Move by a relative distance in mm or degrees (see ``pulses_per_unit``)."""
        return self._to_unit(self.move_relative_pulses(self._to_pulses(delta), timeout=timeout))

    def move_relative_range(self, fraction: float, timeout: float = 30.0) -> Optional[float]:
        """Move by a relative distance given as a fraction of the device's full travel."""
        return self._to_range(self.move_relative_pulses(self._from_range(fraction), timeout=timeout))

    def get_home_offset_pulses(self) -> int:
        """HOSTREQ_HOMEOFFSET "go" / DEVGET_HOMEOFFSET "HO"."""
        reply = self._request("go", expect="HO")
        return protocol.decode_long(reply.data)

    def get_home_offset(self) -> float:
        """Distance of the home position from the absolute limit of travel, in units."""
        return self._to_unit(self.get_home_offset_pulses())

    def set_home_offset_pulses(self, offset: int) -> None:
        """HOSTSET_HOMEOFFSET "so"."""
        self._request("so", protocol.encode_long(offset))

    def set_home_offset(self, offset: float) -> None:
        self.set_home_offset_pulses(self._to_pulses(offset))

    def get_jog_step_size_pulses(self) -> int:
        """HOSTREQ_JOGSTEPSIZE "gj" / DEVGET_JOGSTEPSIZE "GJ"."""
        reply = self._request("gj", expect="GJ")
        return protocol.decode_long(reply.data)

    def get_jog_step_size(self) -> float:
        return self._to_unit(self.get_jog_step_size_pulses())

    def set_jog_step_size_pulses(self, step: int) -> None:
        """HOSTSET_JOGSTEPSIZE "sj". A step of 0 enables continuous motion on ELL14 (use with `stop()`)."""
        self._request("sj", protocol.encode_long(step))

    def set_jog_step_size(self, step: float) -> None:
        self.set_jog_step_size_pulses(self._to_pulses(step))

    def get_velocity(self) -> int:
        """HOSTREQ_VELOCITY "gv" / DEVGET_VELOCITY "GV". Percent of max velocity."""
        reply = self._request("gv", expect="GV")
        return protocol.decode_char(reply.data)

    def set_velocity(self, percent: int) -> None:
        """HOSTSET_VELOCITY "sv". 25-45%+ typical minimum before stalling; 50% minimum on ELL16/ELL21."""
        if not (0 <= percent <= 100):
            raise ValueError("velocity percent must be 0-100")
        self._request("sv", protocol.encode_char(percent))

    def stop(self) -> None:
        """HOST_MOTIONSTOP "st". Stops continuous motion (ELL14) or an optimize/clean cycle.

        Confirmed on real hardware: this does *not* interrupt a bounded
        ``move_absolute``/``move_relative``/``home`` once issued -- the
        move keeps running until the physical motion completes, exactly as
        if ``stop()`` was never called. It only affects continuous jog
        motion (jog step size 0, started via ``forward``/``backward``) or
        an in-progress optimize/clean cycle.

        Sent as an urgent, queue-bypassing write (see
        ``ElliptecBus.send_urgent``) rather than a normal request, since
        the whole point is interrupting a command that's *already in
        flight* -- that job's own read loop is what's occupying the bus, so
        a normal request would just queue harmlessly behind it. Doesn't
        wait for a reply; call ``get_status()``/``get_position()``
        afterward if you need to confirm the outcome.
        """
        self.bus.send_urgent(self.address, "st")


class AutoHomingMixin:
    """ah: ELL15 motorized iris only."""

    def set_auto_homing_pulses(self, enabled: bool, timeout: float = 30.0) -> Optional[int]:
        """HOSTSET_AUTOHOMING "ah". Home-at-startup toggle for the ELL15."""
        reply = self.bus.request(
            self.address, "ah", protocol.encode_char(1 if enabled else 0), timeout=timeout
        )
        return self._position_from_move_reply(reply)

    def set_auto_homing(self, enabled: bool, timeout: float = 30.0) -> Optional[float]:
        """Home-at-startup toggle for the ELL15. Returns the resulting position in units."""
        return self._to_unit(self.set_auto_homing_pulses(enabled, timeout=timeout))


class OptimizeCleanMixin:
    """om, cm, st: ELL14/15/16/17/18/20/21/22. ``supports_clean`` gates `cm` (ELL15 lacks it)."""

    supports_clean: bool = True

    def optimize_motors(self, timeout: float = 300.0) -> StatusCode:
        """HOST_OPTIMIZE_MOTORS "om". Can take several minutes; occupies the whole bus."""
        reply = self.bus.request(self.address, "om", expect="GS", timeout=timeout)
        return StatusCode(reply.as_status_code())

    def clean_mechanics(self, timeout: float = 300.0) -> StatusCode:
        """HOST_CLEAN_MECHANICS "cm". Can take several minutes; occupies the whole bus."""
        self._require(self.supports_clean, "the mechanical cleaning cycle")
        reply = self.bus.request(self.address, "cm", expect="GS", timeout=timeout)
        return StatusCode(reply.as_status_code())

    def stop(self) -> None:
        """HOST_MOTIONSTOP "st". Aborts an in-progress optimize/clean cycle.

        Sent as an urgent, queue-bypassing write (see
        ``ElliptecBus.send_urgent``) since the optimize/clean command
        already in flight is what's occupying the bus; a normal request
        would just queue behind it. Doesn't wait for a reply -- call
        ``get_status()`` afterward if you need to confirm the abort.
        """
        self.bus.send_urgent(self.address, "st")


class ZeroPositionMixin:
    """sz, gz: ND filter rotator (ELL22) only."""

    def set_zero_position(self) -> StatusCode:
        """HOSTSET_ZEROPOSITION "sz". Makes the current encoder position the new logical zero."""
        reply = self._request("sz", expect="GS", raise_on_error=False)
        return StatusCode(reply.as_status_code())

    def get_zero_position_offset_pulses(self) -> int:
        """HOSTGET_ZEROPOSITION "gz" / DEVGET_ZEROPOSITION "ZO"."""
        reply = self._request("gz", expect="ZO")
        return protocol.decode_long(reply.data)

    def get_zero_position_offset(self) -> float:
        return self._to_unit(self.get_zero_position_offset_pulses())


class ResetFactoryMixin:
    """rd: ELL22 only. Restarts the device."""

    def reset_factory_default(self) -> None:
        """HOSTREQ_RESETFACTORY_DEFAULT "rd"."""
        self.bus.send(self.address, "rd")
