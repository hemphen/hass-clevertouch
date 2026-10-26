"""Test startup failures and recovery."""

from datetime import timedelta
from typing import Any
from unittest.mock import patch

from aiohttp import ClientConnectionError, ServerTimeoutError
from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(ClientConnectionError("Offline"), id="connection-error"),
        pytest.param(ServerTimeoutError("Offline"), id="timeout"),
    ],
)
async def test_setup_retries_until_api_recovers(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_api: AiohttpClientMockResponse,
    aioclient_mock: AiohttpClientMocker,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    freezer: FrozenDateTimeFactory,
    error: Exception,
) -> None:
    """A failed initial refresh must not leave a loaded entry with no entities."""
    mock_api.exc = error
    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    assert "clevertouch" not in hass.data
    assert not dr.async_entries_for_config_entry(device_registry, config_entry.entry_id)
    assert not er.async_entries_for_config_entry(entity_registry, config_entry.entry_id)
    assert aioclient_mock.call_count == 1

    freezer.tick(timedelta(seconds=4))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert aioclient_mock.call_count == 1

    freezer.tick(timedelta(seconds=2))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    assert aioclient_mock.call_count == 2

    mock_api.exc = None
    freezer.tick(timedelta(seconds=9))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert aioclient_mock.call_count == 2

    freezer.tick(timedelta(seconds=2))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert config_entry.state is ConfigEntryState.LOADED
    assert len(hass.states.async_all("climate")) == 3
    assert (
        len(er.async_entries_for_config_entry(entity_registry, config_entry.entry_id))
        == 28
    )
    assert (
        len(dr.async_entries_for_config_entry(device_registry, config_entry.entry_id))
        == 6
    )
    assert not hass.config_entries.flow.async_progress()


@pytest.mark.parametrize(
    "status", [pytest.param(400, id="bad-token"), pytest.param(401, id="unauthorized")]
)
async def test_setup_auth_failure_starts_reauth(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_api: AiohttpClientMockResponse,
    device_registry: dr.DeviceRegistry,
    status: int,
) -> None:
    """A rejected token requires reauth instead of loading an empty integration."""
    mock_api.status = status
    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    assert "clevertouch" not in hass.data
    assert not dr.async_entries_for_config_entry(device_registry, config_entry.entry_id)
    assert not hass.states.async_all("climate")
    flows = hass.config_entries.flow.async_progress()
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == SOURCE_REAUTH
    assert flows[0]["context"]["entry_id"] == config_entry.entry_id


@pytest.mark.usefixtures("mock_api")
async def test_resource_401_retries_without_reauth(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_user_read: AiohttpClientMockResponse,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Access-token rejection should retry setup without demanding new credentials."""
    mock_user_read.status = 401

    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    assert not hass.config_entries.flow.async_progress()
    assert aioclient_mock.call_count == 2

    mock_user_read.status = 200
    freezer.tick(timedelta(seconds=6))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert config_entry.state is ConfigEntryState.LOADED
    assert len(hass.states.async_all("climate")) == 3
    assert not hass.config_entries.flow.async_progress()
    refreshes = [
        call for call in aioclient_mock.mock_calls if call[1].path.endswith("/token")
    ]
    assert len(refreshes) == 2


@pytest.mark.usefixtures("mock_api")
async def test_empty_home_discovery_is_refreshed(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    home_data: list[dict[str, Any]],
    mock_user_read: AiohttpClientMockResponse,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """An initially empty cached user must not stop subsequent discovery reads."""
    with patch.object(
        mock_user_read,
        "json",
        return_value={
            "code": {"code": "1", "key": "ok", "value": "OK"},
            "data": {"user_id": "offline-user", "smarthomes": []},
        },
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    assert aioclient_mock.call_count == 2

    # No entities exist yet to subscribe to coordinator polling.
    coordinator = hass.data["clevertouch"][config_entry.entry_id]
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    user_reads = [
        call
        for call in aioclient_mock.mock_calls
        if call[1].path == "/api/v0.1/human/user/read/"
    ]
    home_reads = [
        call[2]["smarthome_id"]
        for call in aioclient_mock.mock_calls
        if call[1].path == "/api/v0.1/human/smarthome/read/"
    ]
    assert len(user_reads) == 2
    assert set(home_reads) == {home["smarthome_id"] for home in home_data}
    assert config_entry.state is ConfigEntryState.LOADED


async def test_outage_logged_once_and_recovery(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_api: AiohttpClientMockResponse,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Repeated poll failures log once, and recovery restores availability."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    caplog.clear()
    mock_api.status = 503
    freezer.tick(timedelta(hours=1, seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert (
        hass.states.get("climate.living_room_living_room_radiator").state
        == "unavailable"
    )
    assert (
        len(
            [
                record
                for record in caplog.records
                if record.levelno >= 30 and "clevertouch" in record.name
            ]
        )
        == 1
    )

    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert (
        len(
            [
                record
                for record in caplog.records
                if record.levelno >= 30 and "clevertouch" in record.name
            ]
        )
        == 1
    )

    mock_api.status = 200
    freezer.tick(timedelta(seconds=121))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get("climate.living_room_living_room_radiator").state == "heat"
    assert (
        "Fetching clevertouch-purmo-offline@example.invalid data recovered"
        in caplog.text
    )
