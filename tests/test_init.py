"""Test startup failures and recovery."""

from datetime import timedelta

from aiohttp import ClientConnectionError, ServerTimeoutError
from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant.test_util.aiohttp import (
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
