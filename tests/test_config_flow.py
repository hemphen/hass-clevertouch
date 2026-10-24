"""Test reauthentication without contacting the cloud."""

from unittest.mock import patch

from aiohttp import ClientConnectionError, ServerTimeoutError
import pytest
from pytest_homeassistant.common import MockConfigEntry
from pytest_homeassistant.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType


@pytest.fixture
def auth_response(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMockResponse:
    """Return a synthetic password-grant response."""
    return aioclient_mock.request(
        "post",
        "https://auth.e3.lvi.eu/realms/purmo/protocol/openid-connect/token",
        json={
            "access_token": "offline-access",
            "refresh_token": "reauth-refresh",
            "expires_in": 3600,
        },
    )


@pytest.mark.usefixtures("auth_response")
@pytest.mark.parametrize(
    "unique_id",
    [
        pytest.param("offline@example.invalid", id="existing-unique-id"),
        pytest.param(None, id="legacy-entry-without-unique-id"),
    ],
)
async def test_reauth_updates_original_entry(
    hass: HomeAssistant, config_entry: MockConfigEntry, unique_id: str | None
) -> None:
    """Update the initiating entry while retaining its identity and custom data."""
    original_data = {**config_entry.data, "retained_setting": "keep"}
    hass.config_entries.async_update_entry(
        config_entry,
        unique_id=unique_id,
        title="My heating",
        data=original_data,
        options={"retained_option": True},
    )
    other_entry = MockConfigEntry(
        domain="clevertouch",
        unique_id="other@example.invalid",
        data={"username": "other@example.invalid", "token": "other-refresh"},
    )
    other_entry.add_to_hass(hass)

    with patch.object(
        hass.config_entries, "async_reload", return_value=True
    ) as reload_entry:
        result = await config_entry.start_reauth_flow(hass)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "reauth_confirm"
        assert not result["errors"]

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"password": "offline-password"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    reload_entry.assert_awaited_once_with(config_entry.entry_id)
    assert config_entry.data == {**original_data, "token": "reauth-refresh"}
    assert config_entry.title == "My heating"
    assert config_entry.options == {"retained_option": True}
    assert config_entry.unique_id == unique_id
    assert len(hass.config_entries.async_entries("clevertouch")) == 2
    assert other_entry.data["token"] == "other-refresh"


@pytest.mark.parametrize(
    ("status", "error", "expected_error"),
    [
        pytest.param(400, None, "invalid_auth", id="invalid-credentials-400"),
        pytest.param(401, None, "invalid_auth", id="invalid-credentials-401"),
        pytest.param(
            200,
            ClientConnectionError("Offline"),
            "cannot_connect",
            id="connection-error",
        ),
        pytest.param(
            200, ServerTimeoutError("Offline"), "cannot_connect", id="timeout"
        ),
    ],
)
async def test_reauth_errors_allow_retry(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    auth_response: AiohttpClientMockResponse,
    status: int,
    error: Exception | None,
    expected_error: str,
) -> None:
    """Show credential/network errors and recover in the same flow."""
    original_data = dict(config_entry.data)
    auth_response.status = status
    auth_response.exc = error
    with patch.object(
        hass.config_entries, "async_reload", return_value=True
    ) as reload_entry:
        result = await config_entry.start_reauth_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"password": "offline-password"}
        )
        await hass.async_block_till_done()

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "reauth_confirm"
        assert result["errors"] == {"base": expected_error}
        assert config_entry.data == original_data
        assert len(hass.config_entries.async_entries("clevertouch")) == 1
        reload_entry.assert_not_called()

        auth_response.status = 200
        auth_response.exc = None
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"password": "offline-password"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data == {**original_data, "token": "reauth-refresh"}
    assert len(hass.config_entries.async_entries("clevertouch")) == 1
    reload_entry.assert_awaited_once_with(config_entry.entry_id)
