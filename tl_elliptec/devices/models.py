"""Concrete classes for every ELLx module covered by the protocol manual.

Capability composition follows the per-command "applicability" notes in
the manufacturer manual (not the summary index tables at the end of the
manual, which are inconsistent with the per-command notes and with each
other)::

    Model     Travel type          Motors  Motion cmds  Optimize/Clean  Extras
    ELL6      31mm slider (index)  1                                   -
    ELL6B     31mm slider (index)  2                                   -
    ELL9      31mm slider (index)  2                                   -
    ELL12     19mm slider (index)  2                                   -
    ELL14     360 deg rotary       2       yes          both            -
    ELL15     iris                 2       yes          optimize only   auto-homing
    ELL16     360 deg rotary       2       yes          both            no f/b tuning, no buttons
    ELL17     28mm linear          2       yes          both            -
    ELL18     360 deg rotary       2       yes          both            -
    ELL20     60mm linear          2       yes          both            -
    ELL21     360 deg rotary       2       yes          both            no f/b tuning, no buttons
    ELL22     360 deg filter rot.  2       yes          both            no f/b tuning, no buttons,
                                                                         zero-position, factory reset
"""
from __future__ import annotations

from .base import (
    AutoHomingMixin,
    ElliptecDevice,
    MotionMixin,
    OptimizeCleanMixin,
    ResetFactoryMixin,
    ZeroPositionMixin,
)


class ELL6(ElliptecDevice):
    """Bi-positional slider, 1 motor, 31mm indexed travel."""

    has_motor2 = False


class ELL6B(ElliptecDevice):
    """Multi-position slider, 2 motors, 31mm indexed travel."""


class ELL9(ElliptecDevice):
    """Multi-position slider, 2 motors, 31mm indexed travel."""


class ELL12(ElliptecDevice):
    """Multi-position slider, 2 motors, 19mm indexed travel."""


class ELL14(MotionMixin, OptimizeCleanMixin, ElliptecDevice):
    """Rotary stage, 360 deg, 398 pulses/deg."""

    DEFAULT_PULSES_PER_UNIT = 398.0  # pulses/degree
    PULSES_FIELD_IS_PER_REVOLUTION = True  # get_info() reports 143360 pulses/rev, not 398 pulses/deg


class ELL15(AutoHomingMixin, MotionMixin, OptimizeCleanMixin, ElliptecDevice):
    """Motorized iris."""

    supports_clean = False  # "cm" is not offered for the ELL15
    DEFAULT_PULSES_PER_UNIT = 1000.0  # pulses across the iris travel, per the manual's device table


class ELL16(MotionMixin, OptimizeCleanMixin, ElliptecDevice):
    """Rotary stage, 360 deg, 182 pulses/deg."""

    supports_motor_tuning = False
    supports_button_messages = False
    DEFAULT_PULSES_PER_UNIT = 182.0  # pulses/degree
    PULSES_FIELD_IS_PER_REVOLUTION = True  # get_info() reports 65536 pulses/rev, not 182 pulses/deg


class ELL17(MotionMixin, OptimizeCleanMixin, ElliptecDevice):
    """Linear stage, 28mm, 1024 pulses/mm."""

    DEFAULT_PULSES_PER_UNIT = 1024.0  # pulses/mm
    # get_info() reports 1024 directly as pulses/mm here, not pulses over
    # the full 28mm travel, so no PULSES_FIELD_IS_PER_REVOLUTION correction.


class ELL18(MotionMixin, OptimizeCleanMixin, ElliptecDevice):
    """Rotary stage, 360 deg, 398 pulses/deg."""

    DEFAULT_PULSES_PER_UNIT = 398.0  # pulses/degree
    PULSES_FIELD_IS_PER_REVOLUTION = True  # get_info() reports 143360 pulses/rev, not 398 pulses/deg


class ELL20(MotionMixin, OptimizeCleanMixin, ElliptecDevice):
    """Linear stage, 60mm, 1024 pulses/mm."""

    DEFAULT_PULSES_PER_UNIT = 1024.0  # pulses/mm


class ELL21(MotionMixin, OptimizeCleanMixin, ElliptecDevice):
    """Rotary stage, 360 deg, 182 pulses/deg."""

    supports_motor_tuning = False
    supports_button_messages = False
    DEFAULT_PULSES_PER_UNIT = 182.0  # pulses/degree
    PULSES_FIELD_IS_PER_REVOLUTION = True  # get_info() reports 65536 pulses/rev, not 182 pulses/deg


class ELL22(
    ZeroPositionMixin, ResetFactoryMixin, MotionMixin, OptimizeCleanMixin, ElliptecDevice
):
    """ND filter rotary stage, 360 deg, 182 pulses/deg."""

    supports_motor_tuning = False
    supports_button_messages = False
    DEFAULT_PULSES_PER_UNIT = 182.0  # pulses/degree
    PULSES_FIELD_IS_PER_REVOLUTION = True  # confirmed empirically; get_info() reports pulses/rev


#: Maps the decimal model number (14 for an ELL14, etc.) reported by "in"/"IN"
#: -- decoded from the wire's hex-ASCII "ELL type" field by
#: ``DeviceInfo.from_reply`` -- to its class. Keyed by the plain decimal
#: number on purpose: the hex-vs-decimal conversion belongs at that one wire
#: boundary, not scattered through code that just wants to know "is this an
#: ELL14". Note: ELL6 and ELL6B both report type 6 (they differ only in
#: motor count); the factory disambiguates them by probing for a second motor.
MODEL_REGISTRY: dict[int, type[ElliptecDevice]] = {
    6: ELL6,
    9: ELL9,
    12: ELL12,
    14: ELL14,
    15: ELL15,
    16: ELL16,
    17: ELL17,
    18: ELL18,
    20: ELL20,
    21: ELL21,
    22: ELL22,
}
