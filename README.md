# tl_elliptec

[![Docs](https://readthedocs.org/projects/tl-elliptec/badge/?version=latest)](https://tl-elliptec.readthedocs.io/en/latest/?badge=latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-support-FFDD00?style=flat&logo=buy-me-a-coffee&logoColor=black)](https://www.buymeacoffee.com/tapyr)

Python library for [Thorlabs Elliptec](https://www.thorlabs.com/newgrouppage9.cfm?objectgroup_id=2231) (ELLx) resonant piezo motor modules — rotary stages, linear stages, multi-position sliders, filter wheels, and the motorized iris. Implements the ASCII-hex serial protocol from Thorlabs' own protocol manual, including a priority-based request broker so background position polling never delays a move you're waiting on.

**Full documentation: [tl-elliptec.readthedocs.io](https://tl-elliptec.readthedocs.io)**

> This is an unofficial, community-maintained library. It is not affiliated
> with, endorsed by, or sponsored by Thorlabs, Inc. "Thorlabs" and
> "Elliptec" are trademarks of Thorlabs, Inc., used here only to identify
> the hardware this library talks to.

## Supported devices

ELL6, ELL6B, ELL9, ELL12, ELL14, ELL15, ELL16, ELL17, ELL18, ELL20, ELL21, ELL22.

## Install

```bash
pip install tl_elliptec
```

Or for local development:

```bash
git clone https://github.com/TapyrLabs/tl_elliptec
pip install -e ".[test]"
```

## Quick start

One device wired straight to its controller (no hub) — construct the model
class directly from the serial port; it opens and owns the port itself (Make sure to use the correct COM port for your setup):

```python
from tl_elliptec import ELL20

with ELL20("COM5") as stage:      # "/dev/ttyUSB0" on Linux/macOS
    stage.home()
    stage.move_absolute(10)       # 10 mm — physical units, not raw pulses
    stage.move_relative(-2.5)     # -2.5 mm from wherever it now is
    print(stage.get_position())   # 7.5
```

## Several devices on a shared bus

Create one `ElliptecBus` and hand it to each device — reading and moving
works exactly the same as above, just addressed:

```python
from tl_elliptec import ElliptecBus, discover_devices

with ElliptecBus("COM5") as bus:
    devices = discover_devices(bus)   # probes addresses 0-F, builds the right class for each
    for address, device in devices.items():
        print(address, type(device).__name__, device.serial_number)

    stage = devices["0"]
    stage.home()
    stage.move_absolute(45)           # 45 degrees, if it's an ELL14
```

### First-time address setup

Every ELLx module ships from the factory at address `"0"`. Wire two or more
onto the same bus **before** giving them unique addresses and they all
answer to `"0"` at once — their replies collide on the wire, so neither
`scan()` nor `discover_devices()` finds anything. This has to be fixed once, per device, before they
share the bus. Either let the library walk you through it, always connect one device at a time:

```python
from tl_elliptec import ElliptecBus, setup_devices

with ElliptecBus("COM5") as bus:
    # Connect ONE new, unaddressed device at a time when prompted.
    assigned = setup_devices(bus, count=2)   # e.g. ["1", "2"]
```

...or do it by hand, one device connected at a time:

```python
from tl_elliptec import ElliptecBus, ELL14

with ElliptecBus("COM5") as bus:
    stage = ELL14(bus, address="0")   # factory default, must be the only device on the bus
    stage.change_address("2")         # non-volatile -- a one-time step
```

Addresses persist across power cycles, so this only needs to happen once
per device — after that, `discover_devices()` finds everything normally,
every session.

## Broker-handled communication and live position streaming

Normally, when many devices are connected to a single serial port, and with incessent polling, the communicaiton might go into conflict and brake. tl_elliptec implements a serial communication broker in the `ElliptecBus` class, the broker implements a read/write priority queue for safe command serialization. Explicitly issued commands (moves, reads, ...) always jump
ahead of background polling, so polling a device's position never delays a
move you're waiting on:

```python
for position in stage.poll_position():   # a generator -- only work while it's iterated
    print(position)                       # yields only when the position actually changes
```

This scales to several devices on one bus without extra locking — run one
`poll_position()` per device on its own thread, and issue moves from
another thread (or the main one) whenever you like. 


Full command reference are all in the docs:
**[tl-elliptec.readthedocs.io](https://tl-elliptec.readthedocs.io)**

## Running the tests

```bash
pip install -e ".[test]"
pytest
```

No hardware required — tests run against a scripted fake bus and check
values against the manual's own worked examples.

## License

[MIT](LICENSE) © Matteo Michiardi

---

If this library saved you some time, consider buying me a coffee ☕

[![Buy Me A Coffee](https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png)](https://www.buymeacoffee.com/tapyr)
