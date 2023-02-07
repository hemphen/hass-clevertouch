"""Constants for the Clever Touch E3 integration."""
from clevertouch.devices import TempUnit
from homeassistant.const import UnitOfTemperature

DOMAIN = "clevertouch"

TEMP_NATIVE_UNIT = TempUnit.CELSIUS
TEMP_HA_UNIT = UnitOfTemperature.CELSIUS
TEMP_NATIVE_STEP = 0.5
TEMP_NATIVE_MIN = 5.0
TEMP_NATIVE_MAX = 30
TEMP_NATIVE_PRECISION = 0.1

DEFAULT_SCAN_INTERVAL_SECONDS = 180
QUICK_SCAN_INTERVAL_SECONDS = 15
QUICK_SCAN_COUNT = 3
