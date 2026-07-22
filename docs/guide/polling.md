# Polling position without starving other commands

`poll_position()` is a generator that yields the current position only when
it changes by more than `tolerance` (default 0: any change), polling
roughly every `interval` seconds (default 150ms):

```python
for position in stage.poll_position():
    print(position)   # only fires on an actual change
```

It's a plain generator, not a background thread — it only does work while
something is actively iterating it, so running it inline like the loop
above can never race with other calls you make from the same thread. To
poll continuously *alongside* other work, drive it from its own thread and
stop it with a `threading.Event`:

```python
import threading

stop = threading.Event()

def watch():
    for position in stage.poll_position(stop_event=stop):
        print("moved to", position)

t = threading.Thread(target=watch, daemon=True)
t.start()
...
stop.set()
t.join()
```

`poll_position_pulses` and `poll_position_range` are the same, in raw
pulses and 0..1 fraction-of-travel respectively.

## Why this doesn't collide with other commands, including on a shared bus

Every position poll is issued through the same `ElliptecBus` request path as
everything else, but tagged `RequestPriority.POLL`. The bus owns a single
background worker thread that's the only thing touching the serial port;
every call to `request()`/`send()`/`read_reply()` — from any thread, for
any device on the bus — submits a job to that worker through a priority
queue and blocks until its own job runs. A `RequestPriority.COMMAND` job
(the default for every explicitly issued call: moves, reads, addressing...)
always jumps ahead of any `POLL` jobs still waiting their turn, even if they
were queued first. So you can run one `poll_position()` loop per device — 4
devices on one hub means 4 poller threads sharing one bus — while issuing
moves and other commands from a 5th thread (or the main thread) whenever
you like, and the movement/read commands are never held up behind routine
polling.

```{note}
Priority only reorders jobs still waiting in the queue — it can't
preempt one that's already executing. While any single device is
mid-move, the shared serial link is genuinely occupied for that whole
physical duration; nothing else (for that device or any other) can be
sent or received until it's done. That's a property of the shared bus
itself, not something software can route around.
```

## Live device registry, for streaming several devices' positions at once

`ElliptecBus` also has a small built-in convenience layer for cases where
you want the bus itself to remember what's connected and stream position
updates for everything at once — handy for e.g. an RPC/GUI host that
reflects over an `ElliptecBus` instance's own methods:

```python
bus.refresh_devices()          # (re-)scans and remembers what's connected
for update in bus.stream_positions():
    print(update)               # {"1": {"pulses": ..., "units": ...}, ...}
```

`refresh_devices()` mutates the registry in place, so an already-running
`stream_positions()` generator picks up newly discovered devices on its next
tick without needing to be restarted.
