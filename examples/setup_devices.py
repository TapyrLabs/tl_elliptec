"""One-time setup: assign unique addresses to a batch of factory-default
(address "0") ELLx devices, so they can share a bus afterwards.

Every ELLx module ships at address "0". Two or more of them wired onto the
same bus simultaneously all answer to "0" and their replies collide
electrically -- neither bus.scan() nor discover_devices() can see anything
until each device has a unique address. This is a one-time step per device
(addresses are non-volatile), not something you redo every session.

Run this once per new device (or new batch of devices). Follow the prompts:
connect exactly one new, unaddressed device at a time.
"""
from tl_elliptec import ElliptecBus, setup_devices

PORT = "COM5"
HOW_MANY_NEW_DEVICES = 2

with ElliptecBus(PORT) as bus:
    assigned = setup_devices(bus, count=HOW_MANY_NEW_DEVICES)
    print("Assigned addresses:", assigned)

    # From here on, all of them can stay connected together.
    from tl_elliptec import discover_devices

    devices = discover_devices(bus)
    print(f"found {len(devices)} device(s): {list(devices)}")
