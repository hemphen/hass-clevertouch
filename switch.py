"""CleverTouch switchentities"""
from typing import Optional, Any
import logging

from homeassistant.components.switch import (
    SwitchEntityDescription,
    SwitchEntity,
    SwitchDeviceClass,
)

from homeassistant.config_entries import ConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from clevertouch.devices import Outlet

from .const import (
    DOMAIN,
)
from .coordinator import CleverTouchUpdateCoordinator, CleverTouchEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up CleverTouch number entities."""
    coordinator: CleverTouchUpdateCoordinator = hass.data[DOMAIN].get(entry.entry_id)

    entities = [
        OutletEntity(coordinator, device)
        for home in coordinator.homes.values()
        for device in home.devices.values()
        if isinstance(device, Outlet)
    ]

    async_add_entities(entities)


class OutletEntity(CleverTouchEntity, SwitchEntity):
    """Representation of a CleverTouch configurable temperature."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: CleverTouchUpdateCoordinator, outlet: Outlet
    ) -> None:
        super().__init__(coordinator, outlet)

        self._outlet = outlet
        self.entity_description = SwitchEntityDescription(
            icon="mdi:power-plug",
            device_class=SwitchDeviceClass.OUTLET,
            name="",
            key="outlet",
        )
        self._attr_unique_id = f"{outlet.device_id}-{self.entity_description.key}"

    @property
    def is_on(self) -> Optional[bool]:
        return self._outlet.is_on

    @property
    def icon(self) -> Optional[str]:
        return "mdi:power-plug" if self.is_on else "mdi:power-plug-off"

    async def async_turn_on(self, **kwargs: Any) -> None:
        if self.is_on:
            return
        await self._outlet.set_onoff_state(True)
        await self.coordinator.async_request_delayed_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        if not self.is_on:
            return
        await self._outlet.set_onoff_state(False)
        await self.coordinator.async_request_delayed_refresh()
