"""Example: a single ELL20 wired directly to its controller (no hub/bus)."""
from tl_elliptec import ELL20

PORT = "COM5"

# Construct straight from the port; the device owns and opens the serial
# port itself (no need to create an ElliptecBus by hand). Calibration
# (pulses_per_unit) is queried from the device automatically at construction
# time via "in"; if that fails (e.g. device still booting) it silently falls
# back to ELL20.DEFAULT_PULSES_PER_UNIT until you call refresh_calibration().
with ELL20(PORT) as stage:
    info = stage.get_info()
    print(f"SN={info.serial_number} travel={info.travel}mm pulses/mm={info.pulses_per_unit}")

    stage.home()
    stage.move_absolute(10)          # 10 mm, physical units
    print("position (mm):", stage.get_position())

    stage.move_relative(-2.5)        # -2.5 mm
    print("position (mm):", stage.get_position())

    # Raw encoder-pulse variants are available too, if you need them:
    print("position (pulses):", stage.get_position_pulses())
