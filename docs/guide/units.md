# Physical units vs. raw encoder pulses

`move_absolute`, `move_relative`, `get_position`, `home`, `forward`,
`backward`, `get_home_offset`/`set_home_offset`, and
`get_jog_step_size`/`set_jog_step_size` all work in **mm or degrees**,
converted using the device's `pulses_per_unit`. That factor is queried from
the device (`get_info()`) automatically at construction time; if no device
answers yet, it falls back to a per-model default (e.g. 398 pulses/degree
for the ELL14) until you call `stage.refresh_calibration()`.

Every one of those methods has a `_pulses` twin (`move_absolute_pulses`,
`get_position_pulses`, ...) that bypasses unit conversion entirely and
works in raw encoder pulses, matching the wire protocol 1:1.

```python
stage.move_absolute(10)                 # 10 mm
stage.move_absolute_pulses(10240)       # same move, in raw pulses (if 1024 pulses/mm)
stage.pulses_per_unit                   # 1024.0
```

## The rotary pulses-per-revolution correction

On rotary stages (ELL14/16/18/21/22), `get_info()`'s reported pulse count is
empirically pulses-per-full-revolution (e.g. 143360 for the ELL14), not
pulses-per-degree as its name suggests — the library divides by the
device's reported travel (360°) to get the real pulses/degree used by
`pulses_per_unit` and the unit methods above. Linear stages and sliders
don't need this correction; their reported field already is pulses/mm or
pulses/position.

## Range_rate unit

`move_absolute`, `move_relative`, and `home` also have `_range` twins
(`move_absolute_range`, `move_relative_range`, `home_range`), along with
`get_position_range`, that work in a **0..1 fraction of the device's full
travel** instead — the raw, uncorrected ratio, handy for e.g. driving a
progress bar without knowing the physical units:

```python
stage.move_absolute_range(0.5)          # halfway across the full travel range
stage.get_position_range()              # 0.5
stage.pulses_per_full_range             # 143360, on an ELL14
```
