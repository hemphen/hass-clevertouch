"""The Clever Touch E3 integration."""

from __future__ import annotations

from homeassistant.helpers import device_registry
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .coordinator import CleverTouchUpdateCoordinator

from .const import DOMAIN

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Clever Touch E3 from a config entry."""

    if not entry.unique_id:
        username = entry.data.get(CONF_USERNAME)
        if username:
            hass.config_entries.async_update_entry(entry, unique_id=username)

    session = async_get_clientsession(hass)
    coordinator = CleverTouchUpdateCoordinator(hass, entry=entry, session=session)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    reg = device_registry.async_get(hass)

    for home_id, home in coordinator.homes.items():
        reg.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, coordinator.get_unique_home_id(home_id))},
            manufacturer=coordinator.model.manufacturer,
            model=coordinator.model.controller,
            name=f"{home.info.label} {coordinator.model.controller}",
            suggested_area=home.info.label,
            configuration_url=f"https://{coordinator.host}",
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
