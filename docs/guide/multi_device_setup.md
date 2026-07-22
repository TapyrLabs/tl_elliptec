# First-time setup for multiple devices on one bus

Every ELLx module ships from the factory at address `"0"`. If you wire two
or more of them onto the same bus **before** giving them unique addresses,
they all answer to `"0"` at once and their replies collide on the wire —
neither `scan()` nor `discover_devices()` will find anything, even though
electrically everything is fine. This isn't a bug to work around in
software; it's inherent to the (unarbitrated) multidrop protocol, and it
has to be fixed by addressing each device once, individually, before they
share the bus:

```python
from tl_elliptec import ElliptecBus, setup_devices, discover_devices

with ElliptecBus("COM5") as bus:
    # Connect ONE new, unaddressed device at a time when prompted.
    assigned = setup_devices(bus, count=2)
    print("assigned:", assigned)          # e.g. ["1", "2"]

    # Addresses are non-volatile -- from now on, all of them can stay
    # connected together and just be discovered normally, every session:
    devices = discover_devices(bus)
```

If two unaddressed devices are *already* colliding at `"0"` when you start,
disconnect down to one of them first — {py:func}`~tl_elliptec.setup_devices`
has no way to un-collide two devices that are already both answering to the
same address; it can only address them one at a time as you connect them.
Pass a custom `wait_for_next_device(index, total)` callback to drive the
"connect the next one" step from a GUI instead of the default `input()`
prompt.
