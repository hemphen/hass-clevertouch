"""Coordinator for CleverTouch."""

from __future__ import annotations

from aiohttp import ClientSession
from datetime import timedelta, datetime
import logging
from enum import Enum
from random import randint

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_TOKEN,
    CONF_USERNAME,
    CONF_MODEL,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo

from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.exceptions import ConfigEntryAuthFailed

from .const import (
    DOMAIN,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    QUICK_SCAN_INTERVAL_SECONDS,
    QUICK_SCAN_COUNT,
    MODELS,
    DEFAULT_MODEL_ID,
)
from clevertouch import (
    Account,
    Home,
    User,
    ApiAuthError,
    ApiError,
)
from clevertouch.devices import Device


MIN_BACKOFF_SECONDS = 60
MAX_BACKOFF_SECONDS = 1800
_LOGGER = logging.getLogger(__name__)

type CleverTouchConfigEntry = ConfigEntry[CleverTouchUpdateCoordinator]


class CleverTouchUpdateCoordinator(DataUpdateCoordinator[None]):
    """Class to manage fetching CleverTouch data."""

    config_entry: CleverTouchConfigEntry

    def __init__(
        self, hass: HomeAssistant, *, entry: ConfigEntry, session: ClientSession
    ) -> None:
        """Initialize data updater."""
        self._email = entry.data.get(CONF_USERNAME)
        self.model_id = entry.data.get(CONF_MODEL) or DEFAULT_MODEL_ID
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}-{self.model_id}-{self._email.lower()}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL_SECONDS),
            config_entry=entry,
        )
        self.model = MODELS[self.model_id]
        self.host = self.model.url
        self.account: Account = Account(
            self._email, entry.data[CONF_TOKEN], host=self.host, session=session
        )
        self.user: User | None = None
        self.homes: dict[str, Home] = {}
        self._quick_updates = QuickUpdatesController(
            standard_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL_SECONDS),
            quick_interval=timedelta(seconds=QUICK_SCAN_INTERVAL_SECONDS),
            quick_count=QUICK_SCAN_COUNT,
            min_backoff=timedelta(seconds=MIN_BACKOFF_SECONDS),
            max_backoff=timedelta(seconds=MAX_BACKOFF_SECONDS),
        )

    async def _async_update_token(self) -> None:
        """Handle token updates from the API."""
        _LOGGER.debug("Checking if token should be updated")
        old_token = self.config_entry.data[CONF_TOKEN]
        new_token = self.account.api.refresh_token
        if old_token != new_token:
            _LOGGER.debug("Token updated for %s", self._email)
            new_data = self.config_entry.data.copy()
            new_data[CONF_TOKEN] = new_token
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=new_data
            )

    async def async_request_delayed_refresh(self) -> None:
        """Request delayed (and quicker) updates after setting a variable."""
        if self._quick_updates.request_quick_update():
            await self.async_refresh()

    async def _async_update_data(self) -> None:
        """Fetch data from CleverTouch."""
        _LOGGER.debug("Updating data from the CleverTouch API")
        do_update_now, self.update_interval = self._quick_updates.on_updating()
        if not do_update_now:
            _LOGGER.debug("Update skipped.")
            return

        try:
            if not self.homes:
                self.user = await self.account.get_user()
                self.homes = {
                    home_id: await self.account.get_home(home_id)
                    for home_id in self.user.homes
                }
                _LOGGER.debug(
                    "Retrieved %d new homes from CleverTouch", len(self.homes)
                )
            else:
                for home in self.homes.values():
                    await home.refresh()
                _LOGGER.debug("Refreshed homes from CleverTouch")
            await self._async_update_token()
            self.update_interval = self._quick_updates.on_success()
        except ApiAuthError as ex:
            _LOGGER.error("Authorization failed: %s", ex)
            raise ConfigEntryAuthFailed from ex
        except ApiError as ex:
            _LOGGER.error("API error: %s", ex)
            self.update_interval = self._quick_updates.on_error()
            _LOGGER.info("Backing off %s", self.update_interval)
            raise UpdateFailed from ex
        except Exception as ex:
            _LOGGER.error("Unexpected error: %s, type: %s", ex, type(ex))
            self.update_interval = self._quick_updates.on_error()
            _LOGGER.info("Backing off %s", self.update_interval)
            raise

    def get_unique_home_id(self, home_id) -> str:
        """Return the unique id for a home."""
        return f"{self.model_id}_{home_id}"


class CleverTouchEntity(CoordinatorEntity[CleverTouchUpdateCoordinator]):
    """Base class for a CleverToch entity.

    Used primarily to group entities by a common device.
    """

    def __init__(
        self, coordinator: CleverTouchUpdateCoordinator, device: Device
    ) -> None:
        """Initialize the entity."""
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
        """Return a unique ID to use for this entity."""

        return f"{self.coordinator.model_id}_{self.device.device_id}_{self.entity_description.key}"


class QuickUpdatesController:
    """Class to manipulate the frequency of updates in the data coordinator."""

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

    class State(Enum):
        """Internal state of the quick updates controller."""

        STANDARD = "standard"
        QUICK = "quick"
        BACKING_OFF = "backing_off"

    def __init__(
        self,
        standard_interval: timedelta,
        quick_interval: timedelta,
        quick_count: int,
        min_backoff: timedelta,
        max_backoff: timedelta,
    ) -> None:
        """Initialize the quick updates controller."""

        self._standard_interval: timedelta = standard_interval
        self._quick_interval: timedelta = quick_interval
        self._quick_count: int = quick_count
        self._min_backoff: timedelta = min_backoff
        self._max_backoff: timedelta = max_backoff

        self._state = self.State.STANDARD

        # Until we know better, set the internal state to trigger an
        # immediate update when requested
        now = datetime.now()
        self._current_backoff: timedelta | None = None
        self._last_run_at: datetime = now
        self._next_expected_at: datetime = now
        self._last_expected_at: datetime = now

    def on_error(self) -> timedelta:
        """Handle an error."""
        if self._state == self.State.BACKING_OFF:
            self._current_backoff = min(self._current_backoff * 2, self._max_backoff)
        else:
            self._state = self.State.BACKING_OFF
            self._current_backoff = self._min_backoff
        return self._get_current_interval()

    def on_success(self) -> timedelta:
        """Handle a successful update."""
        if self._state == self.State.BACKING_OFF:
            self._state = self.State.STANDARD
            self._current_backoff = None
        return self._get_current_interval()

    def _get_current_interval(self) -> timedelta:
        match self._state:
            case self.State.STANDARD:
                return self._standard_interval
            case self.State.QUICK:
                return self._quick_interval
            case self.State.BACKING_OFF:
                return self._current_backoff

    def request_quick_update(self, *, count: int | None = None) -> bool:
        """Request quick update(s).

        This method should be called when one (or more) update(s) should
        be run at a higher frequency than normal, but with a delay.

        If the method returns True, an update should be requested immediately
        by the caller, e.g:

        if self._quc.request_quick_update():
            self.async_request_refresh()
        """
        now = datetime.now()

        interval = self._quick_interval
        count = self._quick_count

        # Valid values if this was the only request to take into account
        next_expected_at = now + interval * 0.9
        last_expected_at = now + interval * (count - 0.1)

        # Update time of the last expected quick update if later than before
        self._last_expected_at = max(self._last_expected_at, last_expected_at)

        # Always push the update forward, regardless if it was requested already
        self._next_expected_at = next_expected_at

        match self._state:
            case self.State.STANDARD:
                _LOGGER.debug("Quick updates were requested")
                return True
            case self.State.QUICK:
                _LOGGER.debug("Quick updates were requested (already active)")
                return False
            case self.State.BACKING_OFF:
                _LOGGER.debug("Quick updates were requested, but backing off")
                return False

    def on_updating(self) -> tuple[bool, timedelta | None]:
        """Determine action and next interval when updating.

        This method should be called on every call to the update method.
        A tuple (do_update, update_interval) is returned and an
        actual update should only be run if 'do_update' is true.

        The update interval should always be updated to the returned
        'update_interval', e.g.:

        do_update, self.update_interval = self._quc.on_updating()
        if not do_update:
            return
        """
        now = datetime.now()

        match self._state:
            case self.State.STANDARD:
                self._next_expected_at = now + self._standard_interval * 0.9
                return True, self._standard_interval

            case self.State.QUICK:
                if now < self._next_expected_at:  # An extra refresh
                    _LOGGER.debug(
                        "Quick update requested. Should be skipped - too early. Waiting %s",
                        self._interval,
                    )
                    return False, self._interval

                if now < self._last_expected_at:
                    _LOGGER.debug(
                        "Running quick update - not finished - then waiting %s",
                        self._quick_interval,
                    )
                    return True, self._quick_interval

                self._state = self.State.STANDARD
                _LOGGER.debug(
                    "Final quick update, going back to regular interval: %s",
                    self._standard_interval,
                )
                return True, self._standard_interval

            case self.State.BACKING_OFF:
                _LOGGER.debug(
                    "Backing off, current interval: %s",
                    self._current_backoff,
                )
                return True, self._current_backoff
