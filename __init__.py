"""The Clever Touch E3 integration."""
from __future__ import annotations

from homeassistant.helpers import device_registry
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import CleverTouchUpdateCoordinator

from .const import DOMAIN

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Clever Touch E3 from a config entry."""

    coordinator = CleverTouchUpdateCoordinator(hass, entry=entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    reg = device_registry.async_get(hass)
    reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, coordinator.unique_id)},
        manufacturer="Purmo",
        model="Touch E3",
        name="Touch E3",
        configuration_url="https://e3.lvi.eu/",
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
