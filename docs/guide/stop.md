# The `stop()` caveat

`stop()` (`HOST_MOTIONSTOP "st"`) is sent as an urgent, queue-bypassing
write ({py:meth}`~tl_elliptec.ElliptecBus.send_urgent`) rather than a normal
request, since it's meant to interrupt a command that's *already in
flight* — a normal `request()` call would just queue behind whatever's
occupying the bus and land after the fact.

```{important}
Confirmed on real hardware: **`stop()` does not interrupt a bounded
`move_absolute`/`move_relative`/`home`** once issued — the move runs to
completion regardless of calling `stop()`. It only stops continuous jog
motion (jog step size 0) or aborts an in-progress `optimize_motors`/
`clean_mechanics` cycle.
```

There is no documented way to abort a bounded move once it has been sent —
only continuous-motion jogging (started with a jog step size of 0, via
`forward()`/`backward()`) can be stopped mid-flight.

`stop()` doesn't wait for or return a reply — call
`get_status()`/`get_position()` afterward if you need to confirm the
outcome.
