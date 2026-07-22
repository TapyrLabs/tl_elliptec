"""Example: read/write motor frequency parameters and run a frequency search."""
from tl_elliptec import ElliptecBus, create_device

PORT = "COM5"
ADDRESS = "0"

with ElliptecBus(PORT) as bus:
    device = create_device(bus, ADDRESS)

    info1 = device.get_motor_info(1)
    print(f"motor1 fwd={info1.forward_frequency_hz} Hz bwd={info1.backward_frequency_hz} Hz")

    # Run an automatic frequency search, then persist the result.
    device.search_frequency(1)
    device.save_user_data()

    # Or set an explicit frequency by hand (values in Hz).
    device.set_forward_frequency(1, 78_000)
    device.set_backward_frequency(1, 106_000)
    device.save_user_data()

    # Restore factory defaults for motor 1.
    device.set_forward_period(1, None)
    device.set_backward_period(1, None)
    device.save_user_data()

    # Full current-vs-frequency sweep (takes ~12s on the device).
    curve = device.scan_current_curve(1)
    for sample in curve[:5]:
        print(f"{sample.frequency_hz:.0f} Hz -> {sample.current_amps:.3f} A")
