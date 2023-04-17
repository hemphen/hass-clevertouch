"""CleverTouch number entities"""
from typing import Optional, Callable, Any, Awaitable
import logging

from math import ceil

from homeassistant.components.number import (
    NumberEntityDescription,
    NumberEntity,
    NumberDeviceClass,
)
from homeassistant.config_entries import ConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from clevertouch.devices import Radiator, Device
from clevertouch.devices.radiator import Temperature

from .const import (
    DOMAIN,
    TEMP_HA_UNIT,
    TEMP_NATIVE_UNIT,
    TEMP_NATIVE_STEP,
    TEMP_NATIVE_MIN,
    TEMP_NATIVE_MAX,
)
from .coordinator import CleverTouchUpdateCoordinator, CleverTouchEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up CleverTouch number entities."""
    coordinator: CleverTouchUpdateCoordinator = hass.data[DOMAIN].get(entry.entry_id)

    entities: list[NumberEntity] = []

    entities.extend(
        [
            TemperatureNumberEntity(coordinator, device, temp.name)
            for home in coordinator.homes.values()
            for device in home.devices.values()
            if isinstance(device, Radiator)
            for temp in device.temperatures.values()
            if temp.is_writable and temp.name
        ]
    )

    def _get_boost_time(dev: Device) -> Optional[int]:
        return (
            ceil(dev.boost_time / (60.0 * 60.0)) if isinstance(dev, Radiator) else None
        )

    async def _set_boost_time(dev: Device, value: int) -> None:
        if isinstance(dev, Radiator):
            await dev.set_boost_time(value * 60 * 60)

    entities.extend(
        [
            CleverNumberEntity(
                coordinator,
                device,
                NumberEntityDescription(
                    name="Boost time preset",
                    key="boost_time_preset",
                    native_min_value=0,
                    native_step=1,
                    native_unit_of_measurement="h",
                ),
                _get_boost_time,
                _set_boost_time,
            )
            for home in coordinator.homes.values()
            for device in home.devices.values()
            if isinstance(device, Radiator)
        ]
    )

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
        self._radiator = radiator

        self.entity_description = NumberEntityDescription(
            icon="mdi:thermometer",
            name=f"{self._temp_name} temperature",
            key=f"temp_{self._temp_name}",
            device_class=NumberDeviceClass.TEMPERATURE,
            native_unit_of_measurement=TEMP_HA_UNIT,
            native_step=TEMP_NATIVE_STEP,
            native_max_value=TEMP_NATIVE_MAX,
            native_min_value=TEMP_NATIVE_MIN,
        )

    @property
    def native_value(self) -> Optional[float]:
        temp = self._radiator.temperatures[self._temp_name].as_unit(TEMP_NATIVE_UNIT)
        if isinstance(temp, float):
            temp = round(temp, 1)
        return temp

    async def async_set_native_value(self, value: float) -> None:
        if value == self.native_value:
            return
        await self._radiator.set_temperature(self._temp_name, value, TEMP_NATIVE_UNIT)
        self._radiator.temperatures[self._temp_name] = Temperature(
            value,
            TEMP_NATIVE_UNIT,
            is_writable=True,
            name=self._temp_name,
        )
        await self.coordinator.async_request_delayed_refresh()


class CleverNumberEntity(CleverTouchEntity, NumberEntity):
    """Representation of a CleverTouch read-only duration."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CleverTouchUpdateCoordinator,
        device: Device,
        description: NumberEntityDescription,
        getter: Callable[[Device], Any],
        setter: Callable[[Device, Any], Awaitable[None]],
    ) -> None:
        super().__init__(coordinator, device)
        self._get_value = getter
        self._set_value = setter
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self._get_value(self.device)

    async def async_set_native_value(self, value: Any) -> None:
        if value == self.native_value:
            return
        await self._set_value(self.device, value)
        await self.coordinator.async_request_delayed_refresh()
