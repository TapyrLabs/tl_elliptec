"""End-to-end example: connect to an Elliptec hub, discover devices, move one."""

from tl_elliptec import ElliptecBus, discover_devices

PORT = "COM5"  # e.g. "COM5" on Windows, "/dev/ttyUSB0" on Linux

with ElliptecBus(PORT) as bus:
    devices = discover_devices(bus)
    print(f"found {len(devices)} device(s): {list(devices)}")

    for address, device in devices.items():
        # discover_devices() already queried "in" to pick the right class;
        # that result is cached on the device as `.info` (and `.serial_number`
        # as a shortcut), so this doesn't cost another round trip.
        info = device.info
        print(
            f"[{address}] {type(device).__name__} "
            f"SN={info.serial_number} FW={info.firmware_release} "
            f"travel={info.travel} pulses/unit={info.pulses_per_unit}"
        )

    # Talk to the device at address "0" (adjust to whatever discover_devices found).
    stage = devices["0"]

    status = stage.get_status()
    print("status:", status)

    motor1 = stage.get_motor_info(1)
    print(
        f"motor1: on={motor1.motor_on} current={motor1.current_amps:.2f}A "
        f"fwd={motor1.forward_frequency_hz} Hz bwd={motor1.backward_frequency_hz} Hz"
    )

    # Homing / absolute-move commands are only on rotary/linear/iris stages
    # (MotionMixin), not on multi-position sliders (ELL6/ELL6B/ELL9/ELL12).
    # move_absolute/move_relative/get_position work in physical units (mm or
    # degrees), converted using the device's calibrated pulses_per_unit; use
    # the *_pulses variants (e.g. move_absolute_pulses) to bypass conversion.
    if hasattr(stage, "home"):
        stage.home()
        position = stage.move_absolute(10)  # 10 mm or degrees, depending on the stage
        print("position after move:", position)
