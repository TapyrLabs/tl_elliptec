# devices

Every command in the manual, split by what it applies to:

- **All devices** ({py:class}`~tl_elliptec.devices.base.ElliptecDevice`):
  `get_info`, `refresh_calibration`, `get_status`, `save_user_data`,
  `change_address`, `isolate_minutes`, `group_address`,
  `skip_frequency_search`, `get_motor_info(1|2)`,
  `set_forward_period`/`set_forward_frequency`,
  `set_backward_period`/`set_backward_frequency`, `search_frequency`,
  `scan_current_curve`, `get_position`/`get_position_pulses`,
  `forward`/`forward_pulses`, `backward`/`backward_pulses`,
  `get_button_status` (non-blocking poll for spontaneous BS/BO messages).
- **Rotary / linear / iris stages** (`MotionMixin` — not multi-position
  sliders): `home`/`home_pulses`, `move_absolute`/`move_absolute_pulses`,
  `move_relative`/`move_relative_pulses`,
  `get_home_offset`/`set_home_offset` (+ `_pulses` variants),
  `get_jog_step_size`/`set_jog_step_size` (+ `_pulses` variants),
  `get_velocity`/`set_velocity`, `stop` (see {doc}`../guide/stop`).
- **ELL15 iris** (`AutoHomingMixin`): `set_auto_homing`/`set_auto_homing_pulses`.
- **ELL14/15/16/17/18/20/21/22** (`OptimizeCleanMixin`): `optimize_motors`,
  `clean_mechanics` (not on ELL15), `stop`.
- **ELL22** (`ZeroPositionMixin`, `ResetFactoryMixin`): `set_zero_position`,
  `get_zero_position_offset`/`get_zero_position_offset_pulses`,
  `reset_factory_default`.

Capability gating (e.g. no `f1`/`b1` tuning or button messages on
ELL16/ELL21/ELL22; no second motor on ELL6) follows the individual "THIS
MESSAGE DOES NOT APPLY TO..." notes attached to each command in the
manual, since the summary applicability tables at the end of the document
are inconsistent with those notes and with each other. Calling an
unsupported method raises {py:class}`~tl_elliptec.exceptions.ElliptecUnsupportedError`
instead of sending a doomed command to the device.

## Base class and capability mixins

```{automodule} tl_elliptec.devices.base
:members:
:undoc-members:
```

## Concrete models

```{automodule} tl_elliptec.devices.models
:members:
:undoc-members:
```
