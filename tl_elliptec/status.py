"""Status/error codes returned by GS, BS and other status-bearing replies."""
from __future__ import annotations

from enum import IntEnum


class StatusCode(IntEnum):
    OK = 0
    COMMUNICATION_TIMEOUT = 1
    MECHANICAL_TIMEOUT = 2
    COMMAND_ERROR_OR_NOT_SUPPORTED = 3
    VALUE_OUT_OF_RANGE = 4
    MODULE_ISOLATED = 5
    MODULE_OUT_OF_ISOLATION = 6
    INITIALIZING_ERROR = 7
    THERMAL_ERROR = 8
    BUSY = 9
    SENSOR_ERROR = 10
    MOTOR_ERROR = 11
    OUT_OF_RANGE = 12
    OVER_CURRENT_ERROR = 13

    @classmethod
    def _missing_(cls, value):
        return None


STATUS_MESSAGES = {
    0: "OK, no error",
    1: "Communication time out",
    2: "Mechanical time out",
    3: "Command error or not supported",
    4: "Value out of range",
    5: "Module isolated",
    6: "Module out of isolation",
    7: "Initializing error",
    8: "Thermal error",
    9: "Busy",
    10: "Sensor Error (may appear during self-test; if it persists there is an error)",
    11: "Motor Error (may appear during self-test; if it persists there is an error)",
    12: "Out of Range (e.g. stage instructed to move beyond its travel range)",
    13: "Over Current error",
}


def describe(code: int) -> str:
    if 14 <= code <= 255:
        return "Reserved"
    return STATUS_MESSAGES.get(code, f"Unknown status code {code}")
