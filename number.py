"""CleverTouch number entities"""
from typing import Optional
import logging

from homeassistant.components.number import (
    NumberEntityDescription,
    NumberEntity,
    NumberDeviceClass,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.config_entries import ConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN
from .clevertouch.clevertouch import Radiator
from .coordinator import CleverTouchUpdateCoordinator, CleverTouchEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up CleverTouch number entities."""
    coordinator: CleverTouchUpdateCoordinator = hass.data[DOMAIN].get(entry.entry_id)

    entities = [
        TemperatureNumberEntity(coordinator, device, temp.name)
        for home in coordinator.homes.values()
        for device in home.devices.values()
        if device.type == Radiator.DEVICE_RADIATOR
        for temp in device.temperatures.values()
        if temp.is_writable
    ]

    async_add_entities(entities)


class TemperatureNumberEntity(CleverTouchEntity, NumberEntity):
    """Representation of a CleverTouch configurable temperature."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CleverTouchUpdateCoordinator,
        radiator: Radiator,
        temp_name: str,
    ) -> None:
        super().__init__(coordinator, radiator)

        self._temp_name = temp_name

        self.entity_description = NumberEntityDescription(
            icon="mdi:thermometer",
            name=f"{self._temp_name} temperature",
            key=f"temp_{self._temp_name}",
            entity_category=EntityCategory.CONFIG,
            device_class=NumberDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
            native_step=0.1,
        )
        self._attr_unique_id = f"{radiator.device_id}-{self.entity_description.key}"

    @property
    def _radiator(self) -> Radiator:
        return self.device

    @property
    def native_value(self) -> Optional[float]:
        return self._radiator.temperatures[self._temp_name].farenheit
