# Quick start

## Point-to-point (one controller, one device — no hub)

This is the common case: a single device wired straight to its controller.
Construct the model class directly from the serial port; it opens and owns
the port itself.

```python
from tl_elliptec import ELL20

with ELL20("COM5") as stage:               # "/dev/ttyUSB0" on Linux/macOS
    stage.home()
    stage.move_absolute(10)                # 10 mm, physical units
    print(stage.get_position())            # mm
```

## Shared bus (a hub with several addressed devices)

Create an `ElliptecBus` once and hand it to each device (address `0`-`F`);
none of them owns or closes the shared port.

```python
from tl_elliptec import ElliptecBus, discover_devices

with ElliptecBus("COM5") as bus:
    devices = discover_devices(bus)        # probes addresses 0-F, instantiates the right class
    for address, device in devices.items():
        print(address, type(device).__name__, device.serial_number)

    stage = devices["0"]
    stage.home()
    stage.move_absolute(45)                # 45 degrees, if it's an ELL14

    # Or skip discovery if you already know the address and model:
    from tl_elliptec import ELL14
    other = ELL14(bus, address="2")
    other.set_velocity(80)
    other.move_relative(-5)
```

Every device caches the `DeviceInfo` from the `"in"` query already made to
identify it (during {py:func}`~tl_elliptec.discover_devices`/
{py:func}`~tl_elliptec.create_device`, or at construction time for a
directly-instantiated device) as `.info`, with `.serial_number` as a
shortcut — no extra round trip needed to see what's connected:
`device.info.travel`, `device.info.firmware_release`, `device.serial_number`,
etc. `.info` is `None` only if the device has never successfully answered an
`"in"` request (call `refresh_calibration()` once it's reachable to populate
it).
