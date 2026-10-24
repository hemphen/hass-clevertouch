"""Test publication of library state after accepted entity commands."""

from typing import Any

from clevertouch import ApiConnectError
import pytest
from pytest_homeassistant.common import MockConfigEntry
from pytest_homeassistant.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)

from homeassistant.components.climate import HVACMode
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

CLIMATE_ID = "climate.living_room_living_room_radiator"
pytestmark = pytest.mark.usefixtures("loaded_entry")


@pytest.fixture
async def loaded_entry(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_api: AiohttpClientMockResponse,
    aioclient_mock: AiohttpClientMocker,
) -> AiohttpClientMockResponse:
    """Load synthetic devices and acknowledge commands without changing cloud data."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return aioclient_mock.request(
        "post",
        "https://e3.lvi.eu/api/v0.1/human/query/push/",
        json={"code": {"code": "8", "key": "ok", "value": "OK"}, "data": {}},
    )


@pytest.mark.parametrize(
    ("activation_data", "preset", "device_mode", "target"),
    [
        pytest.param({"mode": "Eco"}, "Eco", "3", 17, id="eco"),
        pytest.param({"mode": "Frost"}, "Frost", "2", 5, id="frost"),
        pytest.param(
            {"mode": "Boost", "temperature": 26, "duration": {"minutes": 10}},
            "Boost",
            "4",
            26,
            id="boost",
        ),
    ],
)
async def test_activation_publishes_and_remembers_preset(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    entity_registry: er.EntityRegistry,
    activation_data: dict[str, Any],
    preset: str,
    device_mode: str,
    target: float,
) -> None:
    """Keep an accepted preset when Heat follows before the next cloud poll."""
    await hass.services.async_call(
        Platform.CLIMATE,
        "set_temperature",
        {"entity_id": CLIMATE_ID, "temperature": 22},
        blocking=True,
    )
    calls_before = aioclient_mock.call_count
    await hass.services.async_call(
        "clevertouch",
        "activate_heat_mode",
        {"entity_id": CLIMATE_ID, **activation_data},
        blocking=True,
    )
    state = hass.states.get(CLIMATE_ID)
    assert state is not None
    assert state.attributes["preset_mode"] == preset
    assert state.attributes["temperature"] == target
    target_id = entity_registry.async_get_entity_id(
        Platform.SENSOR, "clevertouch", "purmo_radiator-1_temp_target"
    )
    assert hass.states.get(target_id).state == str(float(target))

    await hass.services.async_call(
        Platform.CLIMATE,
        "set_hvac_mode",
        {"entity_id": CLIMATE_ID, "hvac_mode": HVACMode.HEAT},
        blocking=True,
    )
    assert hass.states.get(CLIMATE_ID).attributes["preset_mode"] == preset
    modes = [
        call[2]["query[gv_mode]"]
        for call in aioclient_mock.mock_calls
        if "query[gv_mode]" in call[2]
    ]
    assert modes == [device_mode]
    assert aioclient_mock.call_count == calls_before + 1


async def test_failed_activation_keeps_published_preset(
    hass: HomeAssistant,
    loaded_entry: AiohttpClientMockResponse,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """A rejected activation must not change the state or remembered preset."""
    await hass.services.async_call(
        Platform.CLIMATE,
        "set_temperature",
        {"entity_id": CLIMATE_ID, "temperature": 22},
        blocking=True,
    )
    before = hass.states.get(CLIMATE_ID)
    calls_before = aioclient_mock.call_count
    loaded_entry.status = 503
    with pytest.raises(ApiConnectError):
        await hass.services.async_call(
            "clevertouch",
            "activate_heat_mode",
            {"entity_id": CLIMATE_ID, "mode": "Eco"},
            blocking=True,
        )
    await hass.services.async_call(
        Platform.CLIMATE,
        "set_hvac_mode",
        {"entity_id": CLIMATE_ID, "hvac_mode": HVACMode.HEAT},
        blocking=True,
    )
    assert hass.states.get(CLIMATE_ID) == before
    assert aioclient_mock.call_count == calls_before + 1


@pytest.mark.parametrize(
    ("platform", "service", "unique_id", "service_data", "expected_states"),
    [
        pytest.param(
            Platform.CLIMATE,
            "set_temperature",
            "purmo_radiator-1_radiator",
            {"temperature": 23},
            [
                (Platform.NUMBER, "purmo_radiator-1_temp_comfort", "23.0"),
                (Platform.SENSOR, "purmo_radiator-1_temp_target", "23.0"),
            ],
            id="climate-temperature",
        ),
        pytest.param(
            Platform.NUMBER,
            "set_value",
            "purmo_radiator-1_temp_comfort",
            {"value": 23},
            [
                (Platform.NUMBER, "purmo_radiator-1_temp_comfort", "23.0"),
                (Platform.SENSOR, "purmo_radiator-1_temp_target", "23.0"),
            ],
            id="number-temperature",
        ),
        pytest.param(
            Platform.NUMBER,
            "set_value",
            "purmo_radiator-1_boost_time_preset",
            {"value": 2},
            [(Platform.NUMBER, "purmo_radiator-1_boost_time_preset", "2")],
            id="boost-preset",
        ),
        pytest.param(
            Platform.SWITCH,
            "turn_off",
            "purmo_outlet-1_outlet",
            {},
            [(Platform.SWITCH, "purmo_outlet-1_outlet", "off")],
            id="outlet",
        ),
    ],
)
async def test_commands_publish_shared_state_without_a_poll(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    entity_registry: er.EntityRegistry,
    platform: Platform,
    service: str,
    unique_id: str,
    service_data: dict[str, int],
    expected_states: list[tuple[Platform, str, str]],
) -> None:
    """Publish accepted changes across platforms while quick updates are pending."""
    await hass.services.async_call(
        Platform.CLIMATE,
        "set_temperature",
        {"entity_id": CLIMATE_ID, "temperature": 22},
        blocking=True,
    )
    calls_before = aioclient_mock.call_count
    entity_id = entity_registry.async_get_entity_id(platform, "clevertouch", unique_id)
    await hass.services.async_call(
        platform,
        service,
        {"entity_id": entity_id, **service_data},
        blocking=True,
    )
    for state_platform, state_unique_id, expected in expected_states:
        related_id = entity_registry.async_get_entity_id(
            state_platform, "clevertouch", state_unique_id
        )
        assert hass.states.get(related_id).state == expected
    assert aioclient_mock.call_count == calls_before + 1
