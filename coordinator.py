"""Coordinator for CleverTouch."""
from __future__ import annotations
from typing import Optional

from datetime import timedelta
import logging


from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo

from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    # UpdateFailed,
)

from .const import DOMAIN, DEFAULT_SCAN_INTERVAL_SECONDS
from clevertouch import Account, Home
from clevertouch.devices import Device

SCAN_INTERVAL = timedelta(seconds=DEFAULT_SCAN_INTERVAL_SECONDS)
_LOGGER = logging.getLogger(__name__)


class CleverTouchUpdateCoordinator(DataUpdateCoordinator[None]):
    """Class to manage fetching CleverTouch data."""

    def __init__(self, hass: HomeAssistant, *, entry: ConfigEntry) -> None:
        """Initialize data updater."""
        self._email = entry.data[CONF_EMAIL]
        self.api_session: Account = Account(self._email, entry.data[CONF_TOKEN])
        self.homes: dict[str, Home] = {}
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}-{self._email.lower()}",
            update_interval=SCAN_INTERVAL,
        )
        self.delayed_update_status: str = "inactive"
        self.delayed_update_interval: timedelta = timedelta(seconds=30)
        self.standard_update_interval: Optional[timedelta] = SCAN_INTERVAL

    async def async_request_delayed_refresh(self) -> None:
        if self.delayed_update_status == "inactive":
            self.delayed_update_status = "requested"
            await self.async_request_refresh()

    async def _async_update_data(self) -> None:
        """Fetch data from CleverTouch."""
        # Check if delayed update is requested"""
        if self.delayed_update_status == "requested":
            self.delayed_update_status = "pending"
            self.standard_update_interval = self.update_interval
            self.update_interval = self.delayed_update_interval
            _LOGGER.debug("Initiated delayed update in CleverTouch coordinator")
            return

        if self.delayed_update_status == "pending":
            self.delayed_update_status = "inactive"
            self.update_interval = self.standard_update_interval
            _LOGGER.debug("Running delayed update in CleverTouch coordinator")

        if not self.homes:
            user = await self.api_session.get_user()
            self.homes = {
                home_id: await self.api_session.get_home(home_id)
                for home_id in user.homes
            }
            _LOGGER.debug("Retrieved %d from CleverTouch", len(self.homes))
        else:
            for home in self.homes.values():
                await home.refresh()
            _LOGGER.debug("Finished update in CleverTouch coordinator")

    @property
    def unique_id(self) -> str:
        """Return unique id for this coordinator."""
        return self._email.lower()

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
