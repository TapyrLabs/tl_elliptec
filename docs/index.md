# tl_elliptec

Python library for [Thorlabs Elliptec](https://www.thorlabs.com/newgrouppage9.cfm?objectgroup_id=2231)
(ELLx) resonant piezo motor modules — rotary stages, linear stages,
multi-position sliders, filter wheels, and the motorized iris. Implements
the ASCII-hex serial protocol from Thorlabs' own protocol manual over a
multidrop TTL RS-232 / USB bus, including a priority-based request broker so
background position polling never delays a move you're waiting on.

Supported devices: ELL6, ELL6B, ELL9, ELL12, ELL14, ELL15, ELL16, ELL17,
ELL18, ELL20, ELL21, ELL22.

Source and issue tracker: <https://github.com/TapyrLabs/tl_elliptec>

```{note}
This is an unofficial, community-maintained library. It is not affiliated
with, endorsed by, or sponsored by Thorlabs, Inc. "Thorlabs" and "Elliptec"
are trademarks of Thorlabs, Inc., used here only to identify the hardware
this library talks to.
```

## Install

```bash
pip install tl_elliptec
```

## Quick start

A single device wired straight to its controller (no hub) — construct the
model class directly from the serial port; it opens and owns the port
itself:

```python
from tl_elliptec import ELL20

with ELL20("COM5") as stage:      # "/dev/ttyUSB0" on Linux/macOS
    stage.home()
    stage.move_absolute(10)       # 10 mm — physical units, not raw pulses
    print(stage.get_position())   # 10.0
```

Several devices sharing one bus (a hub) — create one `ElliptecBus` and hand
it to each device:

```python
from tl_elliptec import ElliptecBus, discover_devices

with ElliptecBus("COM5") as bus:
    devices = discover_devices(bus)   # probes addresses 0-F, builds the right class for each
    for address, device in devices.items():
        print(address, type(device).__name__, device.serial_number)
```

Continue with the guide below for units, multi-device address setup,
position polling, and the full command reference.

```{toctree}
:maxdepth: 2
:caption: Guide

guide/installation
guide/quickstart
guide/multi_device_setup
guide/units
guide/polling
guide/stop
```

```{toctree}
:maxdepth: 2
:caption: API Reference

api/protocol
api/status
api/exceptions
api/bus
api/factory
api/devices
```
