"""Test user-facing action failures and recovery."""

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant.common import MockConfigEntry
from pytest_homeassistant.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

ENTITY_ID = "climate.living_room_living_room_radiator"


@pytest.mark.parametrize(
    ("token_status", "write_status", "translation_key", "flow_count"),
    [
        pytest.param(401, 200, "invalid_auth", 1, id="invalid-credentials"),
        pytest.param(200, 401, "access_token_rejected", 0, id="access-token"),
        pytest.param(200, 503, "command_failed", 0, id="connection"),
    ],
)
async def test_action_failure_and_retry(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_api: AiohttpClientMockResponse,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
    token_status: int,
    write_status: int,
    translation_key: str,
    flow_count: int,
) -> None:
    """Fail clearly, preserve state, and only request reauth for invalid credentials."""
    hass.config_entries.async_update_entry(config_entry, pref_disable_polling=True)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    before = hass.states.get(ENTITY_ID)
    write = aioclient_mock.request(
        "post",
        "https://e3.lvi.eu/api/v0.1/human/query/push/",
        status=write_status,
        json={"code": {"code": "8", "key": "ok", "value": "OK"}, "data": {}},
    )
    mock_api.status = token_status
    freezer.tick(timedelta(hours=1, seconds=1))
    with pytest.raises(HomeAssistantError) as error:
        await hass.services.async_call(
            Platform.CLIMATE, "turn_off", {"entity_id": ENTITY_ID}, blocking=True
        )
    await hass.async_block_till_done()
    assert error.value.translation_key == translation_key
    assert error.value.translation_domain == "clevertouch"
    assert hass.states.get(ENTITY_ID) == before
    flows = hass.config_entries.flow.async_progress()
    assert len(flows) == flow_count
    assert all(flow["context"]["source"] == "reauth" for flow in flows)
    assert all(flow["context"]["entry_id"] == config_entry.entry_id for flow in flows)
    writes = [
        call
        for call in aioclient_mock.mock_calls
        if call[1].path.endswith("/query/push/")
    ]
    assert len(writes) == 1 - flow_count

    mock_api.status = 200
    write.status = 200
    await hass.services.async_call(
        Platform.CLIMATE, "turn_off", {"entity_id": ENTITY_ID}, blocking=True
    )
    assert hass.states.get(ENTITY_ID).state == "off"
