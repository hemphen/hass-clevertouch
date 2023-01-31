from typing import Optional

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    ClimateEntityDescription,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfTemperature,
)

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from clevertouch.devices import Radiator, DeviceType, HeatMode
from .coordinator import CleverTouchUpdateCoordinator, CleverTouchEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up CleverTouch climate entities."""
    coordinator: CleverTouchUpdateCoordinator = hass.data[DOMAIN].get(entry.entry_id)

    entities = [
        RadiatorEntity(coordinator, device)
        for home in coordinator.homes.values()
        for device in home.devices.values()
        if isinstance(device, Radiator)
    ]

    async_add_entities(
        entities,
        update_before_add=True,
    )


class RadiatorEntity(CleverTouchEntity, ClimateEntity):
    """Representation of a CleverTouch climate entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CleverTouchUpdateCoordinator,
        radiator: Radiator,
    ) -> None:
        super().__init__(coordinator, radiator)

        self._attr_hvac_modes = []  # HVACMode.HEAT, HVACMode.OFF, HVACMode.AUTO]
        self._attr_preset_modes = radiator.modes

        self.entity_description = ClimateEntityDescription(
            icon="mdi:radiator",
            name="Radiator",
            key="radiator",
        )
        self._attr_unique_id = f"{radiator.device_id}-{self.entity_description.key}"

        self._attr_temperature_unit = UnitOfTemperature.FAHRENHEIT
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
        )

    @property
    def _radiator(self) -> Radiator:
        return self.device

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current operation ie. heat, cool, idle."""
        if self._radiator.heat_mode == HeatMode.OFF:
            return HVACMode.OFF
        elif self._radiator.heat_mode == HeatMode.PROGRAM:
            return HVACMode.AUTO
        return HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction:
        if self._radiator.heat_mode == HeatMode.OFF:
            return HVACAction.OFF
        elif self._radiator.active:
            return HVACAction.HEATING
        return HVACAction.IDLE

    @property
    def icon(self) -> Optional[str]:
        if self._radiator.heat_mode == HeatMode.OFF:
            return "mdi:radiator-off"
        elif self._radiator.active:
            return "mdi:radiator"
        return "mdi:radiator-disabled"

    @property
    def current_temperature(self) -> Optional[float]:
        """Return the current temperature."""
        return self._radiator.temperatures["current"].farenheit

    @property
    def target_temperature(self) -> Optional[float]:
        """Return the temperature we try to reach."""
        return self._radiator.temperatures["target"].farenheit

    @property
    def preset_mode(self) -> Optional[str]:
        """Return the preset_mode."""
        return self._radiator.heat_mode
