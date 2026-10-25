"""Test HA persistence of tokens rotated by the API library."""

from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from datetime import timedelta
from functools import partial
from typing import Any
from unittest.mock import patch

from aiohttp import ClientConnectionError
from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant.common import MockConfigEntry
from pytest_homeassistant.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er


@pytest.mark.usefixtures("mock_api")
@pytest.mark.parametrize(
    "issued_refresh_token", [pytest.param("rotated-refresh", id="rotated-token")]
)
@pytest.mark.parametrize(
    ("user_read_error", "home_read_error"),
    [
        pytest.param(ClientConnectionError("Offline"), None, id="failed-user-read"),
        pytest.param(None, ClientConnectionError("Offline"), id="failed-home-read"),
    ],
)
async def test_rotated_token_survives_failed_setup(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Keep a rotated token even when the following data request fails."""
    original = {**config_entry.data, "retained_setting": "keep"}
    hass.config_entries.async_update_entry(config_entry, data=original)
    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    assert config_entry.data == {**original, "token": "rotated-refresh"}


@pytest.mark.usefixtures("mock_api")
@pytest.mark.parametrize(
    ("refresh_token_fields", "stored_token"),
    [
        pytest.param(
            {"refresh_token": "rotated-refresh"}, "rotated-refresh", id="replacement"
        ),
        pytest.param({}, "offline-refresh", id="omitted-replacement"),
    ],
)
async def test_store_only_valid_replacement_token(
    hass: HomeAssistant, config_entry: MockConfigEntry, stored_token: str
) -> None:
    """Do not erase the stored refresh token when no replacement is available."""
    original = {**config_entry.data, "retained_setting": "keep"}
    hass.config_entries.async_update_entry(config_entry, data=original)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.data == {**original, "token": stored_token}


@pytest.mark.usefixtures("mock_api")
@pytest.mark.parametrize("issued_refresh_token", [None, ""])
async def test_malformed_replacement_preserves_stored_token(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Malformed token responses fail setup without erasing stored credentials."""
    original = dict(config_entry.data)

    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    assert config_entry.data == original
    assert not hass.config_entries.flow.async_progress()


@pytest.mark.parametrize(
    ("domain", "entity_domain", "service", "unique_id", "service_data", "initial_on"),
    [
        pytest.param(
            "climate",
            "climate",
            "set_preset_mode",
            "purmo_radiator-1_radiator",
            {"preset_mode": "Off"},
            "1",
            id="climate-mode",
        ),
        pytest.param(
            "climate",
            "climate",
            "set_temperature",
            "purmo_radiator-1_radiator",
            {"temperature": 22},
            "1",
            id="climate-temperature",
        ),
        pytest.param(
            "clevertouch",
            "climate",
            "activate_heat_mode",
            "purmo_radiator-1_radiator",
            {"mode": "Eco"},
            "1",
            id="heat-mode-action",
        ),
        pytest.param(
            "number",
            "number",
            "set_value",
            "purmo_radiator-1_temp_eco",
            {"value": 18},
            "1",
            id="number-temperature",
        ),
        pytest.param(
            "number",
            "number",
            "set_value",
            "purmo_radiator-1_boost_time_preset",
            {"value": 2},
            "1",
            id="number-boost",
        ),
        pytest.param(
            "switch",
            "switch",
            "turn_off",
            "purmo_outlet-1_outlet",
            {},
            "1",
            id="switch-off",
        ),
        pytest.param(
            "switch",
            "switch",
            "turn_on",
            "purmo_outlet-1_outlet",
            {},
            "0",
            id="switch-on",
        ),
    ],
)
@pytest.mark.parametrize(
    ("write_status", "expectation"),
    [
        pytest.param(200, nullcontext, id="success"),
        pytest.param(
            503, partial(pytest.raises, HomeAssistantError), id="failed-write"
        ),
        pytest.param(
            401, partial(pytest.raises, HomeAssistantError), id="rejected-access-token"
        ),
    ],
)
async def test_entity_action_persists_rotated_token(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_api: AiohttpClientMockResponse,
    aioclient_mock: AiohttpClientMocker,
    entity_registry: er.EntityRegistry,
    home_data: list[dict[str, Any]],
    freezer: FrozenDateTimeFactory,
    domain: str,
    entity_domain: str,
    service: str,
    unique_id: str,
    service_data: dict[str, str | int],
    initial_on: str,
    write_status: int,
    expectation: Callable[[], AbstractContextManager[object]],
) -> None:
    """Retain command-triggered rotations on every HA write path, without retries."""
    home_data[0]["devices"][2]["on_off"] = initial_on
    original = {**config_entry.data, "retained_setting": "keep"}
    hass.config_entries.async_update_entry(
        config_entry, data=original, pref_disable_polling=True
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = entity_registry.async_get_entity_id(
        entity_domain, "clevertouch", unique_id
    )
    assert entity_id is not None
    aioclient_mock.post(
        "https://e3.lvi.eu/api/v0.1/human/query/push/",
        status=write_status,
        json={"code": {"code": "8", "key": "ok", "value": "OK"}, "data": {}},
    )
    freezer.tick(timedelta(hours=1, seconds=1))
    with (
        patch.object(
            mock_api,
            "json",
            return_value={
                "access_token": "new-access",
                "refresh_token": "command-refresh",
                "expires_in": 3600,
            },
        ),
        expectation(),
    ):
        await hass.services.async_call(
            domain, service, {"entity_id": entity_id, **service_data}, blocking=True
        )
    await hass.async_block_till_done()

    assert config_entry.data == {**original, "token": "command-refresh"}
    writes = [
        call
        for call in aioclient_mock.mock_calls
        if call[1].path == "/api/v0.1/human/query/push/"
    ]
    refreshes = [
        call for call in aioclient_mock.mock_calls if call[1].path.endswith("/token")
    ]
    assert len(writes) == 1
    assert len(refreshes) == 2
