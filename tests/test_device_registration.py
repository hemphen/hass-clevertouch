"""Test device registration through Home Assistant setup and reload."""

import logging
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

ORIGINAL_ENTITY_ID = "climate.living_room_living_room_radiator"


@pytest.mark.usefixtures("mock_api")
@pytest.mark.parametrize(
    "order",
    [pytest.param(1, id="api-order"), pytest.param(-1, id="reversed-api-order")],
)
async def test_device_registration(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    home_data: list[dict[str, Any]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Register all entities with their existing identities and correct controllers."""
    caplog.set_level(logging.WARNING)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    parents = {
        home["smarthome_id"]: device_registry.async_get_device_by_identifier(
            ("clevertouch", f"purmo_{home['smarthome_id']}"), config_entry.entry_id
        )
        for home in home_data
    }
    for home in home_data:
        parent = parents[home["smarthome_id"]]
        assert parent is not None
        assert parent.name == f"{home['label']} Touch E3"
        assert parent.manufacturer == "Purmo"
        assert parent.model == "Touch E3"
        assert parent.configuration_url == "https://e3.lvi.eu"
        for device in home["devices"]:
            child = device_registry.async_get_device_by_identifier(
                ("clevertouch", f"purmo_{device['id']}"), config_entry.entry_id
            )
            assert child is not None
            assert child.via_device_id == parent.id

    entries = er.async_entries_for_config_entry(entity_registry, config_entry.entry_id)
    assert len(entries) == 28
    assert len(hass.states.async_all("climate")) == 3
    assert len(hass.states.async_all("number")) == 15
    assert len(hass.states.async_all("sensor")) == 9
    assert len(hass.states.async_all("switch")) == 1
    assert (
        entity_registry.async_get_entity_id(
            "climate", "clevertouch", "purmo_radiator-1_radiator"
        )
        == ORIGINAL_ENTITY_ID
    )
    assert "deprecated `via_device`" not in caplog.text

    entity_registry.async_update_entity(
        ORIGINAL_ENTITY_ID,
        new_entity_id="climate.my_radiator",
        name="My radiator",
    )
    devices_before = {
        device.id: (device.identifiers, device.via_device_id)
        for device in dr.async_entries_for_config_entry(
            device_registry, config_entry.entry_id
        )
    }
    entities_before = {
        entity.unique_id: (entity.entity_id, entity.device_id, entity.name)
        for entity in er.async_entries_for_config_entry(
            entity_registry, config_entry.entry_id
        )
    }

    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    assert {
        device.id: (device.identifiers, device.via_device_id)
        for device in dr.async_entries_for_config_entry(
            device_registry, config_entry.entry_id
        )
    } == devices_before
    assert {
        entity.unique_id: (entity.entity_id, entity.device_id, entity.name)
        for entity in er.async_entries_for_config_entry(
            entity_registry, config_entry.entry_id
        )
    } == entities_before
    assert hass.states.get("climate.my_radiator") is not None
    assert "deprecated `via_device`" not in caplog.text
