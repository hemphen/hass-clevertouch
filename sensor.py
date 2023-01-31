"""CleverTouch sensor entities"""
from typing import Optional
import logging

from homeassistant.components.sensor import (
    SensorEntityDescription,
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory

from .const import (
    DOMAIN,
    TEMP_HA_UNIT,
    TEMP_NATIVE_UNIT,
)
from clevertouch.devices import Radiator
from .coordinator import CleverTouchUpdateCoordinator, CleverTouchEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up CleverTouch sensor entities."""
    coordinator: CleverTouchUpdateCoordinator = hass.data[DOMAIN].get(entry.entry_id)

    entities = [
        TemperatureSensorEntity(coordinator, device, temp.name)
        for home in coordinator.homes.values()
        for device in home.devices.values()
        if isinstance(device, Radiator)
        for temp in device.temperatures.values()
        if not temp.is_writable and temp.name
    ]

    async_add_entities(entities)


class TemperatureSensorEntity(CleverTouchEntity, SensorEntity):
    """Representation of a CleverTouch read-only temperature."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CleverTouchUpdateCoordinator,
        radiator: Radiator,
        temp_name_str,
    ) -> None:
        super().__init__(coordinator, radiator)
        self._temp_name = temp_name_str
        self._radiator = radiator

        self.entity_description = SensorEntityDescription(
            icon="mdi:thermometer",
            name=f"{self._temp_name} temperature",
            key=f"temp_{self._temp_name}",
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=TEMP_HA_UNIT,
        )
        self._attr_unique_id = f"{radiator.device_id}-{self.entity_description.key}"

    @property
    def native_value(self) -> Optional[float]:
        temp = self._radiator.temperatures[self._temp_name].as_unit(TEMP_NATIVE_UNIT)
        if isinstance(temp, float):
            temp = round(temp, 1)
        return temp
