"""Python library for Thorlabs Elliptec (ELLx) resonant piezo motor modules.

Talks the ASCII-hex protocol described in the manufacturer's "ELLx
OEM/Bare modules protocol manual" over a multidrop TTL RS-232 / USB bus
(a "hub").

Quick start::

    from tl_elliptec import ElliptecBus, discover_devices

    with ElliptecBus("COM5") as bus:
        devices = discover_devices(bus)
        rotator = devices["0"]
        rotator.home()
        rotator.move_absolute(rotator.get_info().pulses_per_unit * 90)  # 90 deg, if ELL14/18
"""
from .bus import ElliptecBus, Reply, RequestPriority
from .devices import (
    MODEL_REGISTRY,
    AutoHomingMixin,
    CurrentCurveSample,
    DeviceInfo,
    ELL6,
    ELL6B,
    ELL9,
    ELL12,
    ELL14,
    ELL15,
    ELL16,
    ELL17,
    ELL18,
    ELL20,
    ELL21,
    ELL22,
    ElliptecDevice,
    MotionMixin,
    MotorInfo,
    OptimizeCleanMixin,
    ResetFactoryMixin,
    ZeroPositionMixin,
    period_for_frequency,
)
from .exceptions import (
    ElliptecError,
    ElliptecProtocolError,
    ElliptecStatusError,
    ElliptecTimeoutError,
    ElliptecUnsupportedError,
)
from .factory import create_device, discover_devices, setup_devices
from .status import StatusCode

__version__ = "0.1.0"

__all__ = [
    "ElliptecBus",
    "Reply",
    "RequestPriority",
    "ElliptecDevice",
    "DeviceInfo",
    "MotorInfo",
    "CurrentCurveSample",
    "period_for_frequency",
    "MotionMixin",
    "AutoHomingMixin",
    "OptimizeCleanMixin",
    "ZeroPositionMixin",
    "ResetFactoryMixin",
    "MODEL_REGISTRY",
    "ELL6",
    "ELL6B",
    "ELL9",
    "ELL12",
    "ELL14",
    "ELL15",
    "ELL16",
    "ELL17",
    "ELL18",
    "ELL20",
    "ELL21",
    "ELL22",
    "create_device",
    "discover_devices",
    "setup_devices",
    "StatusCode",
    "ElliptecError",
    "ElliptecTimeoutError",
    "ElliptecProtocolError",
    "ElliptecStatusError",
    "ElliptecUnsupportedError",
]
