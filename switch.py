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

from clevertouch.devices import OnOffDevice, DeviceType

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
        CleverTouchSwitchEntity(coordinator, device)
        for home in coordinator.homes.values()
        for device in home.devices.values()
        if isinstance(device, OnOffDevice)
    ]

    async_add_entities(entities)


class CleverTouchSwitchEntity(CleverTouchEntity, SwitchEntity):
    """Representation of a CleverTouch configurable temperature."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: CleverTouchUpdateCoordinator, switch: OnOffDevice
    ) -> None:
        super().__init__(coordinator, switch)

        self._switch = switch
        device_class = (
            SwitchDeviceClass.OUTLET
            if switch.device_type == DeviceType.OUTLET
            else SwitchDeviceClass.SWITCH
        )
        self.entity_description = SwitchEntityDescription(
            device_class=device_class,
            has_entity_name=False,
            key=device_class,
        )

    @property
    def is_on(self) -> Optional[bool]:
        return self._switch.is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        if self.is_on:
            return
        await self._switch.set_onoff_state(True)
        await self.coordinator.async_request_delayed_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        if not self.is_on:
            return
        await self._switch.set_onoff_state(False)
        await self.coordinator.async_request_delayed_refresh()
