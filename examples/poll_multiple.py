"""Example: background position polling for several devices on one shared bus,
while the main thread keeps issuing its own commands (moves, reads, ...).

Each device's poll_position() runs on its own dedicated thread. They all
share a single ElliptecBus, but that's fine: every request (from any
thread, for any device) is arbitrated by the bus's priority broker, and
polling always yields to explicitly issued commands like the ones the main
thread sends below -- see the README section "Polling position without
starving other commands" for how that's implemented.
"""

import threading
import time

from tl_elliptec import ElliptecBus, discover_devices

PORT = "COM12"


def watch(name, device, stop_event):
    for position in device.poll_position(
        interval=0.15, tolerance=0.01, stop_event=stop_event
    ):
        print(f"[{name}] moved to {position:.3f}")


with ElliptecBus(PORT) as bus:
    devices = discover_devices(bus)
    print(f"found {len(devices)} device(s): {list(devices)}")

    stop = threading.Event()
    watchers = [
        threading.Thread(target=watch, args=(addr, dev, stop), daemon=True)
        for addr, dev in devices.items()
    ]
    for t in watchers:
        t.start()

    # Meanwhile, issue ordinary commands from the main thread. These are
    # RequestPriority.COMMAND by default, so they're always serviced ahead
    # of whatever the watcher threads' background polling has queued up.
    try:
        for addr, dev in devices.items():
            if hasattr(dev, "home"):
                dev.home()
        time.sleep(5)  # let the watchers print position updates for a while
    finally:
        stop.set()
        for t in watchers:
            t.join(timeout=2)
