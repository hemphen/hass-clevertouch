"""Constants for the Clever Touch E3 integration."""
from clevertouch.devices import TempUnit
from homeassistant.const import UnitOfTemperature
from collections import namedtuple

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

Model = namedtuple("Model", ["manufacturer", "app", "url", "controller"])

DEFAULT_MODEL_ID = "purmo"
MODELS = {
    "purmo": Model("Purmo", "CleverTouch", "e3.lvi.eu", "Touch E3"),
    "waltermeier": Model(
        "Walter Meier",
        "Walter Meier Smart-Comfort",
        "www.smartcomfort.waltermeier.com",
        "Metalplast Smart-Comfort",
    ),
    "frico": Model(
        "Frico",
        "Frico FP Smart",
        "fricopfsmart.frico.se",
        "Central Unit",
    ),
    "fenix": Model(
        "Fenix", "Fenix V24 Wifi", "v24.fenixgroup.eu", "Smart Home Controller"
    ),
    "vogelundnoot": Model(
        "Vogel & Noot",
        "Vogel & Noot E3",
        "e3.vogelundnoot.com",
        "Touch E3",
    ),
    "cordivari": Model(
        "Cordivari",
        "Cordivari My Way",
        "cordivarihome.com",
        "My Way",
    ),
}
