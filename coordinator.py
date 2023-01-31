"""Coordinator for CleverTouch."""
from __future__ import annotations

from datetime import timedelta
import logging


from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, async_generate_entity_id

from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN
from clevertouch import Account, Home, User
from clevertouch.devices import Device

DEFAULT_SCAN_INTERVAL_SECONDS = 300
SCAN_INTERVAL = timedelta(seconds=DEFAULT_SCAN_INTERVAL_SECONDS)
_LOGGER = logging.getLogger(__name__)


class CleverTouchUpdateCoordinator(DataUpdateCoordinator[None]):
    """Class to manage fetching CleverTouch data."""

    def __init__(self, hass: HomeAssistant, *, entry: ConfigEntry) -> None:
        """Initialize data updater."""
        self.api_session: Account = Account(
            entry.data[CONF_EMAIL], entry.data[CONF_TOKEN]
        )
        self.homes: dict[str, Home] = None
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}-{entry.data[CONF_EMAIL].lower()}",
            update_interval=SCAN_INTERVAL,
        )

    async def _async_update_data(self) -> None:
        """Fetch data from CleverTouch."""
        if self.homes is None:
            user = await self.api_session.get_user()
            self.homes = {
                home_id: await self.api_session.get_home(home_id)
                for home_id in user.homes
            }
            _LOGGER.debug("Retrieved %d from CleverTouch", len(self.homes))
        else:
            for home in self.homes.values():
                await home.refresh()
            _LOGGER.debug("Refreshed CleverTouch coordinator")

    @property
    def unique_id(self) -> str:
        """Return unique id for this coordinator."""
        return self.api_session.email.lower()

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for the main device."""
        return DeviceInfo(identifiers={(DOMAIN, self.unique_id)})


class CleverTouchEntity(CoordinatorEntity[CleverTouchUpdateCoordinator]):
    def __init__(
        self, coordinator: CleverTouchUpdateCoordinator, device: Device
    ) -> None:
        super().__init__(coordinator)
        self.device: Device = device

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.device_id)},
            manufacturer="Purmo",
            model=f"Purmo {device.device_type}",
            name=f"{device.zone.label} {device.label}",
            via_device=(DOMAIN, coordinator.unique_id),
        )
