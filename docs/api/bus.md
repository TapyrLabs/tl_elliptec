# bus

`ElliptecBus` owns the serial port for one multidrop connection: a single
background worker thread services every `request()`/`send()`/`read_reply()`
call through a priority queue (see {doc}`../guide/polling`), so replies are
never interleaved and explicitly issued commands always jump ahead of
background polling.

```{eval-rst}
.. automodule:: tl_elliptec.bus
   :members:
   :undoc-members:
   :exclude-members: _RequestBroker
```
