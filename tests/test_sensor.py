"""Test Boost duration reporting through Home Assistant."""

from typing import Any

import pytest
from pytest_homeassistant.common import MockConfigEntry

from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er


@pytest.mark.usefixtures("mock_api")
@pytest.mark.parametrize(
    ("boost_data", "expected_state"),
    [
        pytest.param(
            {"time_boost_format_chrono": {"m": "5", "s": "21"}},
            "321",
            id="positive-seconds",
        ),
        pytest.param({"time_boost_format_chrono": {"s": "0"}}, "0", id="known-zero"),
        pytest.param({}, STATE_UNKNOWN, id="missing"),
        pytest.param({"time_boost_format_chrono": {}}, STATE_UNKNOWN, id="empty"),
        pytest.param(
            {"time_boost_format_chrono": {"s": "-1"}},
            STATE_UNKNOWN,
            id="negative",
        ),
    ],
)
async def test_boost_time_remaining(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    home_data: list[dict[str, Any]],
    boost_data: dict[str, dict[str, str]],
    expected_state: str,
) -> None:
    """Preserve known zero seconds while leaving missing/invalid values unknown."""
    home_data[0]["devices"][0].update(boost_data)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = entity_registry.async_get_entity_id(
        "sensor", "clevertouch", "purmo_radiator-1_boost_time_remaining"
    )
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == expected_state
    assert state.attributes["unit_of_measurement"] == "s"
