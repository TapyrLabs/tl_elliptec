"""Serial communication with an Elliptec ELLx multidrop bus (a "hub").

A single ELLx interface adapter (USB or TTL RS-232) exposes one serial port
on which up to 16 devices (addresses 0-F) can be daisy-chained. This module
owns the serial port, frames outgoing commands, reads and dispatches replies,
and understands the two-phase reply pattern used by long-running commands
(an interim "GS" busy status followed by a final data reply).

Device-level command objects (see ``tl_elliptec.devices``) are built on top of
an :class:`ElliptecBus` instance and should not talk to ``serial`` directly.

Only one thread ever touches the serial port: a single background worker
owned by :class:`ElliptecBus`. Every public entry point (``request``,
``send``, ``read_reply``) submits a job to that worker through a priority
queue (see :class:`RequestPriority`) and blocks the calling thread until its
own job completes. This is what lets several devices on a shared bus -- and
a background position poller per device -- all issue commands concurrently
from different threads without corrupting each other's replies, while
letting explicitly issued commands (moves, reads, ...) always jump ahead of
low-priority background polling that's still waiting for its turn.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from concurrent.futures import Future
from itertools import count
from typing import Callable, Optional, TypeVar

import serial

from . import protocol
from .exceptions import ElliptecProtocolError, ElliptecStatusError, ElliptecTimeoutError
from .status import StatusCode

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Commands whose reply mnemonic differs from the request but which still
# signal "operation finished" rather than "operation still running".
# GS/BS are always a valid "still busy / error" reply for any request.
_STATUS_COMMANDS = {"GS", "BS"}


class RequestPriority:
    """Ordering used by :class:`ElliptecBus`'s broker (lower value = serviced first).

    ``COMMAND`` is the default for every explicitly issued call (moves,
    status reads, addressing, ...). ``POLL`` is for background/opportunistic
    traffic -- e.g. :meth:`~tl_elliptec.devices.base.ElliptecDevice.poll_position`
    -- so it never delays a command a caller is actively waiting on, even
    when several devices' pollers share one bus.
    """

    COMMAND = 0
    POLL = 10


class Reply:
    """A parsed incoming frame: ``address`` (single hex digit the reply came
    from), ``command`` (2-character reply mnemonic, e.g. ``"GS"`` or
    ``"PO"``), ``data`` (hex-ASCII data payload, may be empty), and ``raw``
    (the raw frame bytes as received, terminator stripped).
    """

    __slots__ = ("address", "command", "data", "raw")

    def __init__(self, address: str, command: str, data: str, raw: bytes):
        """Args:
            address: Single hex-digit address the reply came from.
            command: 2-character reply mnemonic.
            data: Hex-ASCII data payload.
            raw: The raw frame bytes as received.
        """
        self.address = address
        self.command = command
        self.data = data
        self.raw = raw

    def __repr__(self) -> str:
        return f"Reply({self.address}{self.command}{self.data!r})"

    def as_status_code(self) -> int:
        """Interpret this reply's data as a GS/BS status byte.

        Returns:
            The numeric status code (see :class:`~tl_elliptec.status.StatusCode`).
        """
        return protocol.decode_char(self.data)

    def raise_for_status(self) -> None:
        """Raise :class:`~tl_elliptec.exceptions.ElliptecStatusError` if this is a non-OK GS/BS reply.

        Raises:
            ElliptecStatusError: If ``command`` is ``"GS"``/``"BS"`` and the
                status code isn't :attr:`~tl_elliptec.status.StatusCode.OK`.
        """
        if self.command in _STATUS_COMMANDS:
            code = self.as_status_code()
            if code not in (StatusCode.OK,):
                raise ElliptecStatusError(self.address, code)


class _RequestBroker:
    """A single-worker-thread, priority-ordered job queue.

    Generic and serial-agnostic on purpose: it just runs submitted 0-arg
    callables one at a time, in priority order, on its own thread, and
    delivers the result (or exception) back to the submitting thread via a
    ``Future``. Kept separate from :class:`ElliptecBus` so the scheduling
    behavior can be unit tested without a real (or fake) serial port.
    """

    def __init__(self):
        self._queue: "queue.PriorityQueue[tuple[int, int, object]]" = queue.PriorityQueue()
        self._seq = count()
        self._stopped = False
        self._worker = threading.Thread(target=self._run, daemon=True, name="ElliptecBusWorker")
        self._worker.start()

    def submit(self, priority: int, fn: Callable[[], T]) -> "Future[T]":
        future: "Future[T]" = Future()
        if self._stopped:
            future.set_exception(RuntimeError("bus is closed"))
            return future
        self._queue.put((priority, next(self._seq), (fn, future)))
        return future

    def _run(self) -> None:
        while True:
            _priority, _seq, job = self._queue.get()
            if job is None:  # shutdown sentinel
                return
            fn, future = job
            if not future.set_running_or_notify_cancel():
                continue
            try:
                result = fn()
            except BaseException as exc:  # noqa: BLE001 - propagate to the submitter
                future.set_exception(exc)
            else:
                future.set_result(result)

    def stop(self, timeout: Optional[float] = 5.0) -> None:
        if self._stopped:
            return
        self._stopped = True
        # Highest priority so shutdown doesn't wait behind queued low-priority
        # polling, though any job already in flight still runs to completion.
        self._queue.put((-1, next(self._seq), None))
        self._worker.join(timeout=timeout)


class ElliptecBus:
    """Owns the serial port for one Elliptec multidrop (hub) connection.

    Thread-safe: a single background worker owns the serial port and
    services requests from a priority queue (see :class:`RequestPriority`),
    so replies from different addresses on the shared bus are never
    interleaved or misattributed, and commands a caller is actively waiting
    on always preempt queued background polling.
    """

    def __init__(
        self,
        port: str,
        baudrate: int = 9600,
        timeout: float = 2.0,
        serial_kwargs: Optional[dict] = None,
    ):
        """Args:
            port: Serial port name/path, e.g. ``"COM5"`` or ``"/dev/ttyUSB0"``.
            baudrate: Serial baud rate. The protocol is fixed at 9600 8-N-1
                on real hardware; only change this for testing against a
                non-standard transport.
            timeout: Default per-request reply timeout, in seconds. Can be
                overridden per call via ``request()``'s own ``timeout``.
            serial_kwargs: Extra keyword arguments merged into (overriding)
                the ones passed to :class:`serial.Serial`.
        """
        self.port_name = port
        self.timeout = timeout
        kwargs = dict(
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            stopbits=serial.STOPBITS_ONE,
            parity=serial.PARITY_NONE,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
            timeout=timeout,
        )
        if serial_kwargs:
            kwargs.update(serial_kwargs)
        self._serial = serial.Serial(port, **kwargs)
        self._broker = _RequestBroker()
        # Guards the serial port's write side only (not reads) -- see
        # send_urgent() for why writes need their own lock independent of
        # the broker's job queue.
        self._write_lock = threading.Lock()
        # Populated by refresh_devices() below; see that method's docstring.
        self._devices: dict = {}

    def close(self) -> None:
        """Stop the request broker's worker thread and close the serial port."""
        self._broker.stop()
        if self._serial.is_open:
            self._serial.close()

    def __enter__(self) -> "ElliptecBus":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @property
    def is_open(self) -> bool:
        """``True`` if the underlying serial port is currently open."""
        return self._serial.is_open

    # -- framing (normally only called from the broker's worker thread;
    # send_urgent() below is the one exception, by design) --------------

    def _write(self, address: str, command: str, data: str = "") -> None:
        frame = protocol.build_message(address, command, data)
        logger.debug("TX %s", frame)
        with self._write_lock:
            self._serial.write(frame + protocol.LINE_TERMINATOR)
            self._serial.flush()

    def _read_line(self, timeout: Optional[float] = None) -> bytes:
        """Read one CR-LF terminated frame, honoring a per-call timeout override."""
        deadline = time.monotonic() + (timeout if timeout is not None else self.timeout)
        buf = bytearray()
        original_timeout = self._serial.timeout
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ElliptecTimeoutError(
                        f"timed out waiting for reply on {self.port_name}"
                    )
                self._serial.timeout = remaining
                chunk = self._serial.read(1)
                if not chunk:
                    raise ElliptecTimeoutError(
                        f"timed out waiting for reply on {self.port_name}"
                    )
                if chunk == b"\r":
                    continue
                if chunk == b"\n":
                    break
                buf += chunk
        finally:
            self._serial.timeout = original_timeout
        logger.debug("RX %s", bytes(buf))
        return bytes(buf)

    def _read_reply_raw(self, timeout: Optional[float] = None) -> Reply:
        raw = self._read_line(timeout=timeout)
        address, command, data = protocol.parse_message(raw)
        return Reply(address, command, data, raw)

    def _do_request(
        self,
        address: str,
        command: str,
        data: str,
        expect: Optional[str],
        timeout: Optional[float],
        poll_timeout: Optional[float],
        raise_on_error: bool,
        reply_address: Optional[str],
    ) -> Reply:
        """The actual request/reply cycle. Worker-thread-only; see ``request()``."""
        overall_deadline = time.monotonic() + (timeout if timeout is not None else self.timeout)
        expected_reply_address = (reply_address or address).upper()
        self._write(address, command, data)
        while True:
            remaining = overall_deadline - time.monotonic()
            if remaining <= 0:
                raise ElliptecTimeoutError(
                    f"timed out waiting for reply to {address}{command} on {self.port_name}"
                )
            step_timeout = poll_timeout if poll_timeout is not None else remaining
            reply = self._read_reply_raw(timeout=min(step_timeout, remaining))
            if reply.address != expected_reply_address:
                # On a shared multidrop bus a reply may arrive from a
                # different device (e.g. a group-address move); it isn't
                # the answer to this request, so keep waiting for ours.
                logger.debug("ignoring reply from unrelated address %s", reply.address)
                continue
            if reply.command in _STATUS_COMMANDS:
                code = reply.as_status_code()
                if code == StatusCode.BUSY:
                    continue  # keep waiting
                if code != StatusCode.OK and raise_on_error:
                    raise ElliptecStatusError(reply.address, code)
                return reply
            return reply

    # -- public API: safe to call from any thread, arbitrated by the broker --

    def read_reply(self, timeout: Optional[float] = None, priority: int = RequestPriority.COMMAND) -> Reply:
        """Read and parse a single incoming frame (blocking).

        Useful for passively listening for spontaneous BS/BO button-status
        messages, which aren't solicited by a host command.

        Args:
            timeout: Maximum time to wait, in seconds. Defaults to the
                bus's own ``timeout``.
            priority: Scheduling priority against other pending requests
                (see :class:`RequestPriority`).

        Returns:
            The next parsed frame.

        Raises:
            ElliptecTimeoutError: If no frame arrives within ``timeout``.
        """
        return self._broker.submit(priority, lambda: self._read_reply_raw(timeout=timeout)).result()

    def send(self, address: str, command: str, data: str = "", priority: int = RequestPriority.COMMAND) -> None:
        """Send a command with no expectation of a reply being awaited here.

        Args:
            address: Single hex-digit device address.
            command: 2-character command mnemonic.
            data: Optional hex-ASCII data payload.
            priority: Scheduling priority against other pending requests
                (see :class:`RequestPriority`).
        """
        self._broker.submit(priority, lambda: self._write(address, command, data)).result()

    def send_urgent(self, address: str, command: str, data: str = "") -> None:
        """Write directly to the wire, bypassing the request broker's queue entirely.

        Ordinary commands should go through ``request()``/``send()`` so
        they're properly serialized and priority-ordered. This exists for
        the case where that's the wrong tool: sending a command meant to
        affect a device *while some other command for it is already
        executing* -- e.g. HOST_MOTIONSTOP "st" while continuous jog motion
        is running. That other job's worker thread is blocked inside its
        own read loop; a normal ``request("st")`` would just sit in the
        queue until that job finishes on its own. Writing and reading are
        independent operations on a serial port, so this can safely
        interleave with an in-progress read on the broker's worker thread --
        ``_write``'s own lock only guards against two writes landing on the
        wire at once, not against a concurrent read.

        Note: HOST_MOTIONSTOP "st" only interrupts continuous jog motion
        (jog step size 0) or an optimize/clean cycle -- it does not
        interrupt a bounded move_absolute/move_relative/home once issued.
        Sending "st" while a bounded move is in flight is a no-op; that
        move's job keeps running until the physical move completes on its
        own, exactly as if "st" was never sent (see ``MotionMixin.stop``).

        No reply is read here -- whatever job is already in flight for this
        address will see any response on its own next read. Call
        ``get_position()``/``get_status()`` afterward if you need to
        confirm the outcome.

        Args:
            address: Single hex-digit device address.
            command: 2-character command mnemonic, e.g. ``"st"``.
            data: Optional hex-ASCII data payload.
        """
        self._write(address, command, data)

    def request(
        self,
        address: str,
        command: str,
        data: str = "",
        expect: Optional[str] = None,
        timeout: Optional[float] = None,
        poll_timeout: Optional[float] = None,
        raise_on_error: bool = True,
        priority: int = RequestPriority.COMMAND,
        reply_address: Optional[str] = None,
    ) -> Reply:
        """Send a command and wait for its reply.

        Several commands (moves, homing, frequency search, cleaning...) reply
        with one or more interim "GS busy" frames before the final reply
        arrives. This loops, discarding interim busy frames, until either the
        expected reply mnemonic is seen, a non-busy status/error frame is
        seen, or the overall timeout elapses.

        ``expect`` is the reply mnemonic to wait for (e.g. "PO" for a move).
        If omitted, the first non-busy reply is returned regardless of its
        mnemonic.

        ``reply_address`` overrides which address incoming replies must carry
        to be accepted as the answer to this request; defaults to ``address``.
        Needed for HOSTREQ_CHANGEADDRESS ("ca"), the one command where the
        device replies from its *new* address rather than the one the
        command was sent to.

        ``priority`` controls scheduling against other pending requests on
        this bus (see :class:`RequestPriority`); leave it at the default
        unless this call is opportunistic background polling.

        Args:
            address: Single hex-digit device address to send the command to.
            command: 2-character command mnemonic, e.g. ``"in"``.
            data: Optional hex-ASCII data payload.
            expect: Reply mnemonic to wait for, e.g. ``"PO"``. If omitted,
                the first non-busy reply is accepted regardless of mnemonic.
            timeout: Overall deadline for this request, in seconds.
                Defaults to the bus's own ``timeout``.
            poll_timeout: Maximum time to wait for each individual interim
                frame (e.g. a busy status) before re-checking the overall
                deadline. Defaults to the remaining overall timeout.
            raise_on_error: If ``True`` (default), a non-OK GS/BS status
                reply raises :class:`~tl_elliptec.exceptions.ElliptecStatusError`.
            priority: Scheduling priority against other pending requests
                (see :class:`RequestPriority`).
            reply_address: Address incoming replies must carry to be
                accepted; defaults to ``address``.

        Returns:
            The reply that satisfied ``expect`` (or the first non-busy
            reply, if ``expect`` was omitted).

        Raises:
            ElliptecTimeoutError: If no satisfying reply arrives within
                ``timeout``.
            ElliptecStatusError: If ``raise_on_error`` is ``True`` and a
                non-OK GS/BS status reply is received.
        """
        return self._broker.submit(
            priority,
            lambda: self._do_request(
                address, command, data, expect, timeout, poll_timeout, raise_on_error, reply_address
            ),
        ).result()

    def request_status(self, address: str, command: str, data: str = "", **kwargs) -> Reply:
        """Convenience wrapper for commands whose only reply is GS/BS.

        Args:
            address: Single hex-digit device address.
            command: 2-character command mnemonic.
            data: Optional hex-ASCII data payload.
            **kwargs: Forwarded to :meth:`request`.

        Returns:
            The GS/BS status reply.
        """
        return self.request(address, command, data, **kwargs)

    # -- bus scanning ---------------------------------------------------

    def scan(self, addresses: str = protocol.ADDRESS_CHARS, timeout: float = 0.3) -> list[str]:
        """Probe each address with an "in" (get info) request; return the ones that answer.

        Args:
            addresses: Iterable of single-hex-digit addresses to probe.
                Defaults to all 16 (``"0"``-``"F"``).
            timeout: Per-address reply timeout, in seconds.

        Returns:
            The addresses that answered, in the order probed.
        """
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

    # -- live device registry --------------------------------------------
    #
    # A small, optional convenience layer for callers that want the bus
    # itself to remember what's connected and stream position updates for
    # all of it -- e.g. an RPC/GUI host that reflects over an ElliptecBus
    # instance's own methods and has no separate place to keep a devices
    # dict. Purely additive: nothing else in this module depends on it.

    def refresh_devices(self, addresses: str = protocol.ADDRESS_CHARS, timeout: float = 0.3) -> dict:
        """Re-scan the bus and rebuild this bus's known-device registry.

        Returns a plain, JSON-safe dict: ``{address: {ell_type,
        serial_number, travel, pulses_per_unit}}``. ``pulses_per_unit`` is
        the already-corrected value (handles the rotary
        pulses-per-revolution correction internally -- see
        ``ElliptecDevice.PULSES_FIELD_IS_PER_REVOLUTION``), so callers never
        need to reimplement that calibration themselves.

        The registry is mutated in place (``clear()``+``update()``, never
        rebound to a new dict), so an already-running ``stream_positions()``
        generator picks up newly discovered devices on its next tick without
        needing to be restarted.

        Args:
            addresses: Iterable of single-hex-digit addresses to probe.
                Defaults to all 16 (``"0"``-``"F"``).
            timeout: Per-address reply timeout, in seconds.

        Returns:
            A dict keyed by address, each value a dict with keys
            ``ell_type`` (int), ``serial_number`` (str), ``travel`` (int),
            and ``pulses_per_unit`` (float) -- one entry per device found.
        """
        from .factory import discover_devices  # deferred: factory imports devices, which imports this module

        fresh = discover_devices(self, addresses=addresses, timeout=timeout)
        self._devices.clear()
        self._devices.update(fresh)
        return {
            addr: {
                "ell_type": dev.info.ell_type,
                "serial_number": dev.info.serial_number,
                "travel": dev.info.travel,
                "pulses_per_unit": dev.pulses_per_unit,
            }
            for addr, dev in self._devices.items()
            if dev.info is not None
        }

    def stream_positions(self, interval: float = 0.2, tolerance: float = 0.0):
        """Yield ``{address: {"pulses": int, "units": float}}`` for whichever devices in
        this bus's registry (see ``refresh_devices()``) changed by more than
        ``tolerance`` since the last tick.

        One thread, one loop: every device is read sequentially through the
        same request broker each tick, at ``RequestPriority.POLL``, so this
        never adds any concurrency on the serial link beyond what
        ``request()``/``send()`` already handle safely, and never delays an
        explicitly issued command. Meant to be driven by a caller that wants
        continuous position updates (e.g. a WebSocket "subscribe") rather
        than polled directly.

        Reads the registry fresh (via ``list(...)``) each outer-loop pass,
        so devices added by a concurrent ``refresh_devices()`` call show up
        automatically on the next tick -- no need to restart this generator.

        Args:
            interval: Delay between polling ticks, in seconds.
            tolerance: Minimum change (in raw pulses) required to report a
                device's position again; ``0`` reports on any change.

        Yields:
            ``{address: {"pulses": int, "units": float}}`` for whichever
            devices changed by more than ``tolerance`` since the last tick.
            Never yields an empty dict -- if nothing changed, the tick is
            skipped entirely.
        """
        last: dict = {}
        while True:
            changed = {}
            for address, device in list(self._devices.items()):
                try:
                    pulses = device.get_position_pulses(priority=RequestPriority.POLL)
                except Exception:
                    continue
                if address not in last or abs(pulses - last[address]) > tolerance:
                    last[address] = pulses
                    changed[address] = {"pulses": pulses, "units": pulses / device.pulses_per_unit}
            if changed:
                yield changed
            time.sleep(interval)
