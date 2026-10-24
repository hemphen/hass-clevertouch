"""Test standard climate actions against mocked CleverTouch responses."""

import asyncio
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock

from clevertouch import ApiConnectError
from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)
from yarl import URL

from homeassistant.components.climate import ClimateEntityFeature, HVACMode
from homeassistant.core import HomeAssistant

ENTITY_ID = "climate.living_room_living_room_radiator"
ON_ACTIONS = [
    pytest.param("turn_on", {}, id="turn-on"),
    pytest.param("set_hvac_mode", {"hvac_mode": HVACMode.HEAT}, id="heat"),
]
pytestmark = pytest.mark.usefixtures("mock_api")


@pytest.fixture
def initial_mode() -> str:
    """Start the radiator in Comfort unless the test overrides it."""
    return "0"


@pytest.fixture
async def loaded_entry(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_api: AiohttpClientMockResponse,
    home_data: list[dict[str, Any]],
    initial_mode: str,
) -> MockConfigEntry:
    """Load the integration with the selected initial radiator mode."""
    home_data[0]["devices"][0]["gv_mode"] = initial_mode
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


@pytest.fixture
def mock_mode_write(
    aioclient_mock: AiohttpClientMocker, home_data: list[dict[str, Any]]
) -> AsyncMock:
    """Acknowledge writes and expose the accepted mode on the next read."""
    devices = {
        (home["smarthome_id"], device["id_device"]): device
        for home in home_data
        for device in home["devices"]
    }

    async def respond(
        method: str, url: URL, data: dict[str, str]
    ) -> AiohttpClientMockResponse:
        device = devices[(data["smarthome_id"], data["query[id_device]"])]
        device["gv_mode"] = data["query[gv_mode]"]
        return AiohttpClientMockResponse(
            method=method,
            url=url,
            json={"code": {"code": "8", "key": "ok", "value": "OK"}, "data": {}},
        )

    write = AsyncMock(side_effect=respond)
    aioclient_mock.post(
        "https://e3.lvi.eu/api/v0.1/human/query/push/", side_effect=write
    )
    return write


@pytest.mark.usefixtures("loaded_entry")
async def test_supported_modes(hass: HomeAssistant) -> None:
    """Advertise standard heating modes and on/off actions for HomeKit."""
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.attributes["hvac_modes"] == [
        HVACMode.HEAT,
        HVACMode.AUTO,
        HVACMode.OFF,
    ]
    assert state.attributes["supported_features"] & ClimateEntityFeature.TURN_ON
    assert state.attributes["supported_features"] & ClimateEntityFeature.TURN_OFF
    assert state.attributes["preset_modes"] == [
        "Comfort",
        "Eco",
        "Frost",
        "Program",
        "Boost",
        "Off",
    ]


@pytest.mark.usefixtures("loaded_entry")
@pytest.mark.parametrize(
    ("initial_mode", "hvac_mode", "preset", "device_mode"),
    [
        pytest.param("0", HVACMode.OFF, "Off", "1", id="off"),
        pytest.param("0", HVACMode.AUTO, "Program", "11", id="auto"),
        pytest.param("1", HVACMode.HEAT, "Comfort", "0", id="heat-from-off"),
    ],
)
async def test_set_hvac_mode(
    hass: HomeAssistant,
    mock_mode_write: AsyncMock,
    hvac_mode: HVACMode,
    preset: str,
    device_mode: str,
) -> None:
    """Map standard HVAC requests to the expected existing presets."""
    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {"entity_id": ENTITY_ID, "hvac_mode": hvac_mode},
        blocking=True,
    )
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == hvac_mode
    assert state.attributes["preset_mode"] == preset
    assert mock_mode_write.await_count == 1
    assert mock_mode_write.await_args.args[2]["query[gv_mode]"] == device_mode


@pytest.mark.usefixtures("loaded_entry")
@pytest.mark.parametrize(
    ("initial_mode", "preset", "hvac_mode", "device_mode"),
    [
        pytest.param("0", "Comfort", HVACMode.HEAT, "0", id="comfort"),
        pytest.param("3", "Eco", HVACMode.HEAT, "3", id="eco"),
        pytest.param("2", "Frost", HVACMode.HEAT, "2", id="frost"),
        pytest.param("4", "Boost", HVACMode.HEAT, "4", id="boost"),
    ],
)
@pytest.mark.parametrize(("service", "service_data"), ON_ACTIONS)
async def test_on_and_heat_restore_previous_mode(
    hass: HomeAssistant,
    mock_mode_write: AsyncMock,
    preset: str,
    hvac_mode: HVACMode,
    device_mode: str,
    service: str,
    service_data: dict[str, str],
) -> None:
    """Both on actions restore manual presets without preferring Comfort."""
    await hass.services.async_call(
        "climate", "turn_off", {"entity_id": ENTITY_ID}, blocking=True
    )
    assert hass.states.get(ENTITY_ID).state == HVACMode.OFF
    await hass.services.async_call(
        "climate", service, {"entity_id": ENTITY_ID, **service_data}, blocking=True
    )

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == hvac_mode
    assert state.attributes["preset_mode"] == preset
    assert [
        call.args[2]["query[gv_mode]"] for call in mock_mode_write.await_args_list
    ] == ["1", device_mode]


@pytest.mark.usefixtures("loaded_entry")
@pytest.mark.parametrize("initial_mode", [pytest.param("1", id="initially-off")])
@pytest.mark.parametrize(("service", "service_data"), ON_ACTIONS)
async def test_on_and_heat_without_previous_mode(
    hass: HomeAssistant,
    mock_mode_write: AsyncMock,
    service: str,
    service_data: dict[str, str],
) -> None:
    """Use Comfort when no previous active mode has been observed."""
    await hass.services.async_call(
        "climate", service, {"entity_id": ENTITY_ID, **service_data}, blocking=True
    )
    assert hass.states.get(ENTITY_ID).attributes["preset_mode"] == "Comfort"
    assert mock_mode_write.await_args.args[2]["query[gv_mode]"] == "0"


@pytest.mark.usefixtures("loaded_entry")
@pytest.mark.parametrize(
    "initial_mode",
    [
        pytest.param("0", id="comfort"),
        pytest.param("3", id="eco"),
        pytest.param("2", id="frost"),
        pytest.param("4", id="boost"),
    ],
)
@pytest.mark.parametrize(("service", "service_data"), ON_ACTIONS)
async def test_on_and_heat_preserve_active_preset(
    hass: HomeAssistant,
    mock_mode_write: AsyncMock,
    service: str,
    service_data: dict[str, str],
) -> None:
    """Neither on action replaces an active manual heating preset."""
    before = hass.states.get(ENTITY_ID)
    await hass.services.async_call(
        "climate", service, {"entity_id": ENTITY_ID, **service_data}, blocking=True
    )
    assert hass.states.get(ENTITY_ID).state == before.state
    assert (
        hass.states.get(ENTITY_ID).attributes["preset_mode"]
        == before.attributes["preset_mode"]
    )
    mock_mode_write.assert_not_awaited()


@pytest.mark.usefixtures("loaded_entry")
@pytest.mark.parametrize("initial_mode", [pytest.param("8", id="initial-program")])
@pytest.mark.parametrize(
    (
        "service",
        "service_data",
        "preceding_actions",
        "preset",
        "hvac_mode",
        "device_modes",
    ),
    [
        pytest.param(
            "turn_on", {}, [], "Program", HVACMode.AUTO, [], id="on-keeps-program"
        ),
        pytest.param(
            "set_hvac_mode",
            {"hvac_mode": HVACMode.HEAT},
            [],
            "Comfort",
            HVACMode.HEAT,
            ["0"],
            id="heat-leaves-program",
        ),
        pytest.param(
            "turn_on",
            {},
            ["turn_off"],
            "Program",
            HVACMode.AUTO,
            ["1", "11"],
            id="on-restores-program",
        ),
        pytest.param(
            "set_hvac_mode",
            {"hvac_mode": HVACMode.HEAT},
            ["turn_off"],
            "Comfort",
            HVACMode.HEAT,
            ["1", "0"],
            id="heat-does-not-restore-program",
        ),
    ],
)
async def test_program_on_and_heat_have_distinct_behavior(
    hass: HomeAssistant,
    mock_mode_write: AsyncMock,
    service: str,
    service_data: dict[str, str],
    preceding_actions: list[str],
    preset: str,
    hvac_mode: HVACMode,
    device_modes: list[str],
) -> None:
    """Turn on may restore Program, while explicit Heat selects manual Comfort."""
    for action in preceding_actions:
        await hass.services.async_call(
            "climate", action, {"entity_id": ENTITY_ID}, blocking=True
        )
    await hass.services.async_call(
        "climate", service, {"entity_id": ENTITY_ID, **service_data}, blocking=True
    )
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == hvac_mode
    assert state.attributes["preset_mode"] == preset
    assert [
        call.args[2]["query[gv_mode]"] for call in mock_mode_write.await_args_list
    ] == device_modes


@pytest.mark.usefixtures("loaded_entry")
@pytest.mark.parametrize(
    ("preset", "hvac_mode", "device_mode"),
    [
        pytest.param("Off", HVACMode.OFF, "1", id="off"),
        pytest.param("Eco", HVACMode.HEAT, "3", id="eco"),
        pytest.param("Frost", HVACMode.HEAT, "2", id="frost"),
        pytest.param("Program", HVACMode.AUTO, "11", id="program"),
        pytest.param("Boost", HVACMode.HEAT, "4", id="boost"),
    ],
)
async def test_existing_preset_actions(
    hass: HomeAssistant,
    mock_mode_write: AsyncMock,
    preset: str,
    hvac_mode: HVACMode,
    device_mode: str,
) -> None:
    """Keep all existing preset actions working alongside HVAC actions."""
    await hass.services.async_call(
        "climate",
        "set_preset_mode",
        {"entity_id": ENTITY_ID, "preset_mode": preset},
        blocking=True,
    )
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == hvac_mode
    assert state.attributes["preset_mode"] == preset
    assert mock_mode_write.await_args.args[2]["query[gv_mode]"] == device_mode


@pytest.mark.usefixtures("loaded_entry")
@pytest.mark.parametrize("initial_mode", [pytest.param("8", id="remember-program")])
@pytest.mark.parametrize(
    ("service", "service_data"),
    [
        pytest.param("set_preset_mode", {"preset_mode": "Eco"}, id="failed-preset"),
        pytest.param("set_hvac_mode", {"hvac_mode": HVACMode.HEAT}, id="failed-hvac"),
    ],
)
async def test_failed_write_preserves_state_and_previous_mode(
    hass: HomeAssistant,
    mock_mode_write: AsyncMock,
    service: str,
    service_data: dict[str, str],
) -> None:
    """A failed command must not change reported or remembered mode, or be retried."""
    await hass.services.async_call(
        "climate", "turn_off", {"entity_id": ENTITY_ID}, blocking=True
    )
    successful_write = mock_mode_write.side_effect
    mock_mode_write.side_effect = ApiConnectError("Offline")
    with pytest.raises(ApiConnectError):
        await hass.services.async_call(
            "climate", service, {"entity_id": ENTITY_ID, **service_data}, blocking=True
        )
    assert mock_mode_write.await_count == 2
    assert hass.states.get(ENTITY_ID).state == HVACMode.OFF
    assert hass.states.get(ENTITY_ID).attributes["preset_mode"] == "Off"

    mock_mode_write.side_effect = successful_write
    await hass.services.async_call(
        "climate", "turn_on", {"entity_id": ENTITY_ID}, blocking=True
    )
    assert hass.states.get(ENTITY_ID).state == HVACMode.AUTO
    assert hass.states.get(ENTITY_ID).attributes["preset_mode"] == "Program"
    assert mock_mode_write.await_args.args[2]["query[gv_mode]"] == "11"


@pytest.mark.usefixtures("loaded_entry")
async def test_skipped_fetch_keeps_acknowledged_state(
    hass: HomeAssistant, mock_mode_write: AsyncMock, aioclient_mock: AiohttpClientMocker
) -> None:
    """A quick-refresh callback with no cloud read must not undo a successful mode."""
    await hass.services.async_call(
        "climate",
        "set_preset_mode",
        {"entity_id": ENTITY_ID, "preset_mode": "Eco"},
        blocking=True,
    )
    reads_before = aioclient_mock.call_count
    await hass.services.async_call(
        "climate", "turn_off", {"entity_id": ENTITY_ID}, blocking=True
    )
    assert aioclient_mock.call_count == reads_before + 1
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == HVACMode.OFF
    assert state.attributes["hvac_action"] == "off"
    assert state.attributes["icon"] == "mdi:radiator-off"

    await hass.services.async_call(
        "climate", "turn_on", {"entity_id": ENTITY_ID}, blocking=True
    )
    assert hass.states.get(ENTITY_ID).attributes["preset_mode"] == "Eco"


@pytest.mark.usefixtures("loaded_entry")
async def test_polled_mode_is_remembered(
    hass: HomeAssistant,
    mock_mode_write: AsyncMock,
    home_data: list[dict[str, Any]],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Remember a mode selected outside HA when it arrives in a later poll."""
    home_data[0]["devices"][0]["gv_mode"] = "8"
    freezer.tick(timedelta(minutes=3, seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(ENTITY_ID).attributes["preset_mode"] == "Program"
    await hass.services.async_call(
        "climate", "turn_off", {"entity_id": ENTITY_ID}, blocking=True
    )
    await hass.services.async_call(
        "climate", "turn_on", {"entity_id": ENTITY_ID}, blocking=True
    )
    assert hass.states.get(ENTITY_ID).attributes["preset_mode"] == "Program"
    assert mock_mode_write.await_args.args[2]["query[gv_mode]"] == "11"


@pytest.mark.usefixtures("loaded_entry")
@pytest.mark.parametrize(
    ("first_service", "second_service"),
    [
        pytest.param("turn_off", "turn_on", id="off-on"),
        pytest.param("toggle", "toggle", id="toggle-toggle"),
    ],
)
async def test_overlapping_mode_commands(
    hass: HomeAssistant,
    mock_mode_write: AsyncMock,
    home_data: list[dict[str, Any]],
    first_service: str,
    second_service: str,
) -> None:
    """Queued on/toggle requests must evaluate state after the first write succeeds."""
    started = asyncio.Event()
    release = asyncio.Event()

    async def delayed_write(
        method: str, url: URL, data: dict[str, str]
    ) -> AiohttpClientMockResponse:
        started.set()
        await release.wait()
        home_data[0]["devices"][0]["gv_mode"] = data["query[gv_mode]"]
        return AiohttpClientMockResponse(
            method=method,
            url=url,
            json={"code": {"code": "8", "key": "ok", "value": "OK"}, "data": {}},
        )

    mock_mode_write.side_effect = delayed_write
    off = asyncio.create_task(
        hass.services.async_call(
            "climate", first_service, {"entity_id": ENTITY_ID}, blocking=True
        )
    )
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        assert hass.states.get(ENTITY_ID).attributes["preset_mode"] == "Comfort"
        on = asyncio.create_task(
            hass.services.async_call(
                "climate", second_service, {"entity_id": ENTITY_ID}, blocking=True
            )
        )
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(off, on)
    finally:
        release.set()
        await off

    assert [
        call.args[2]["query[gv_mode]"] for call in mock_mode_write.await_args_list
    ] == ["1", "0"]
    assert hass.states.get(ENTITY_ID).attributes["preset_mode"] == "Comfort"


@pytest.mark.usefixtures("loaded_entry")
async def test_activate_heat_mode_is_preserved(
    hass: HomeAssistant,
    mock_mode_write: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Keep the existing action and its optional temperature/duration arguments."""
    await hass.services.async_call(
        "clevertouch",
        "activate_heat_mode",
        {
            "entity_id": ENTITY_ID,
            "mode": "Boost",
            "temperature": 25,
            "duration": {"hours": 1},
        },
        blocking=True,
    )
    payload = mock_mode_write.await_args.args[2]
    assert payload["query[gv_mode]"] == "4"
    assert payload["query[consigne_boost]"] == 770
    assert payload["query[time_boost]"] == 3600
    freezer.tick(timedelta(seconds=16))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(ENTITY_ID).attributes["preset_mode"] == "Boost"
