"""Coordinator for CleverTouch."""
from __future__ import annotations
from typing import Optional

from datetime import timedelta, datetime
import logging


from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_EMAIL,
    CONF_TOKEN,
    CONF_USERNAME,
    CONF_HOST,
    CONF_MODEL,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo

from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    # UpdateFailed,
)

from .const import (
    DOMAIN,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    QUICK_SCAN_INTERVAL_SECONDS,
    QUICK_SCAN_COUNT,
    MODELS,
    DEFAULT_MODEL_ID,
)
from clevertouch import Account, Home, User
from clevertouch.devices import Device

SCAN_INTERVAL = timedelta(seconds=DEFAULT_SCAN_INTERVAL_SECONDS)
_LOGGER = logging.getLogger(__name__)


class CleverTouchUpdateCoordinator(DataUpdateCoordinator[None]):
    """Class to manage fetching CleverTouch data."""

    def __init__(self, hass: HomeAssistant, *, entry: ConfigEntry) -> None:
        """Initialize data updater."""
        self._email = entry.data.get(CONF_USERNAME) or entry.data[CONF_EMAIL]
        self.model_id = entry.data.get(CONF_MODEL) or DEFAULT_MODEL_ID
        self.model = MODELS[self.model_id]
        self.host = entry.data.get(CONF_HOST) or f"https://{self.model.url}"
        self.api_session: Account = Account(
            self._email, entry.data[CONF_TOKEN], host=self.host
        )
        self.user: Optional[User] = None
        self.homes: dict[str, Home] = {}
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}-{self.model_id}-{self._email.lower()}",
            update_interval=SCAN_INTERVAL,
        )
        self._quick_updates = QuickUpdatesController(
            timedelta(seconds=QUICK_SCAN_INTERVAL_SECONDS), count=QUICK_SCAN_COUNT
        )

    async def async_request_delayed_refresh(self) -> None:
        """Request delayed (and quicker) updates after setting a variabled"""
        self._quick_updates.request_quick_update()
        await self.async_refresh()

    async def _async_update_data(self) -> None:
        """Fetch data from CleverTouch."""
        do_update_now, self.update_interval = self._quick_updates.on_updating(
            self.update_interval
        )
        if not do_update_now:
            return

        if not self.homes:
            self.user = await self.api_session.get_user()
            self.homes = {
                home_id: await self.api_session.get_home(home_id)
                for home_id in self.user.homes
            }
            _LOGGER.debug("Retrieved %d new homes from CleverTouch", len(self.homes))
        else:
            for home in self.homes.values():
                await home.refresh()
            _LOGGER.debug("Refreshed homes from CleverTouch")

    def get_unique_home_id(self, home_id) -> str:
        """Return the unique id for a home."""
        return f"{self.model_id}_{home_id}"


class CleverTouchEntity(CoordinatorEntity[CleverTouchUpdateCoordinator]):
    """Base class for a CleverToch entity. Used primarily to group entities
    by a common device."""

    def __init__(
        self, coordinator: CleverTouchUpdateCoordinator, device: Device
    ) -> None:
        super().__init__(coordinator)
        self.device: Device = device

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.model_id}_{device.device_id}")},
            manufacturer=coordinator.model.manufacturer,
            model=f"{device.device_type}",
            name=f"{device.zone.label} {device.label}",
            via_device=(DOMAIN, coordinator.get_unique_home_id(device.home.home_id)),
            suggested_area=device.zone.label,
        )

    @property
    def unique_id(self) -> str | None:
        return f"{self.coordinator.model_id}_{self.device.device_id}_{self.entity_description.key}"


class QuickUpdatesController:
    """Class to manipulate the frequency of updates in the data coordinator"""

    # The background is that when setting a value in the library, it will not
    # be reflected in the GUI until the next update
    #
    # Additionaly, settings take some time to propagate to the devicess and
    # back to the controller.
    #
    # To make updates appear in the interface as quickly and reliably as possible
    # we want to poll the API with a higher frequency right after setting a value
    #
    # Instead of trying to change the behaviour of the DataCoordinator on a more
    # fundamental level, we just tuck on this stateful class that help us modifying
    # the scan interval to increase the frequency of updates on requested.

    INACTIVE = "inactive"
    PENDING = "pending"
    RUNNING = "running"

    def __init__(self, interval: timedelta, *, count: int = 1) -> None:
        self._interval: timedelta = interval
        self._default_count: int = count
        self._status = self.INACTIVE

        # Until we know better, set the internal state to trigger an
        # immediate update when requested
        now = datetime.now()
        self._standard_interval: Optional[timedelta] = interval
        self._last_run_at: datetime = now
        self._next_expected_at: datetime = now
        self._last_expected_at: datetime = now

    def request_quick_update(self, *, count: Optional[int] = None) -> bool:
        """Request quick update(s)

        This method should be called when one (or more) update(s) should
        be run at a higher frequency than normal, but with a delay.

        If the method returns True, an update should be requested immediately
        by the caller, e.g:

        if self._quc.request_quick_update():
            self.async_request_refresh()
        """
        now = datetime.now()

        interval = self._interval
        count = count or self._default_count

        # Valid values if this was the only request to take into account
        next_expected_at = now + interval * 0.9
        last_expected_at = now + interval * (count - 0.1)

        # Update time of the last expected quick update if later than before
        if last_expected_at > self._last_expected_at:
            self._last_expected_at = last_expected_at

        # Always push the update forward, regardless if it was requested already
        self._next_expected_at = next_expected_at

        if self._status == self.INACTIVE:
            self._status = self.PENDING
            _LOGGER.debug("Quick updates were requested")
            return True

        _LOGGER.debug("Quick updates were requested (already active)")
        return False

    def on_updating(
        self, update_interval: Optional[timedelta]
    ) -> tuple[bool, Optional[timedelta]]:
        """Determine action and next interval when updating

        This method should be called on every call to the update method.
        A tuple (do_update, update_interval) is returned and an
        actual update should only be run if 'do_update' is true.

        The update interval should always be updated to the returned
        'update_interval', e.g.:

        do_update, self.update_interval = self._quc.on_updating(self.update_interval)
        if not do_update:
            return
        """
        now = datetime.now()

        if self._status == self.INACTIVE:
            self._standard_interval = update_interval
            interval = update_interval or self._interval
            self._next_expected_at = now + interval * 0.9
            return True, update_interval

        if self._status == self.PENDING:
            _LOGGER.debug(
                "Pending quick update(s), remembering regular interval: %s",
                update_interval,
            )
            self._standard_interval = update_interval
            self._status = self.RUNNING

        if now < self._next_expected_at:  # An extra refresh
            _LOGGER.debug(
                "Quick update requested. Should be skipped - too early. Waiting %s",
                self._interval,
            )
            return False, self._interval

        if now < self._last_expected_at:
            _LOGGER.debug(
                "Running quick update - not finished - then waiting %s",
                self._interval,
            )
            return True, self._interval

        self._status = self.INACTIVE
        _LOGGER.debug(
            "Final quick update, going back to regular interval: %s",
            self._standard_interval,
        )
        return True, self._standard_interval
