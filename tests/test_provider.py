"""Test provider selection at the HA/library boundary."""

from collections.abc import AsyncGenerator
from unittest.mock import ANY, MagicMock, call, patch

from clevertouch import ApiSession, User
import pytest

from homeassistant import loader
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType


@pytest.fixture
async def provider_clients(
    hass: HomeAssistant,
) -> AsyncGenerator[tuple[MagicMock, MagicMock]]:
    """Mock public library clients without assuming provider realm/client settings."""
    integration = await loader.async_get_integration(hass, "clevertouch")
    await integration.async_get_component()
    with (
        patch(
            "custom_components.clevertouch.config_flow.ApiSession", autospec=True
        ) as session_class,
        patch(
            "custom_components.clevertouch.coordinator.Account", autospec=True
        ) as account_class,
    ):
        session_class.return_value.__aenter__.return_value.refresh_token = (
            "provider-refresh"
        )
        account_class.return_value.api = MagicMock(spec=ApiSession)
        account_class.return_value.api.refresh_token = "provider-refresh"
        account_class.return_value.get_user.return_value = MagicMock(
            spec=User, homes={}
        )
        yield session_class, account_class


@pytest.mark.parametrize(
    ("provider", "host"),
    [
        pytest.param("purmo", "e3.lvi.eu", id="purmo"),
        pytest.param("fenix", "v24.fenixgroup.eu", id="fenix"),
    ],
)
async def test_provider_survives_setup_and_reauth(
    hass: HomeAssistant,
    provider_clients: tuple[MagicMock, MagicMock],
    provider: str,
    host: str,
) -> None:
    """Use the selected provider consistently for login, runtime and reauth."""
    session_class, account_class = provider_clients
    result = await hass.config_entries.flow.async_init(
        "clevertouch", context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "username": "offline@example.invalid",
            "password": "offline-password",
            "model": provider,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert entry.state is ConfigEntryState.LOADED
    assert entry.data["model"] == provider
    assert entry.data["token"] == "provider-refresh"
    session_class.assert_called_once_with(host=host, session=ANY)
    account_class.assert_called_once_with(
        "offline@example.invalid", "provider-refresh", host=host, session=ANY
    )
    hass.config_entries.async_update_entry(entry, title="My heating")

    session_class.return_value.__aenter__.return_value.refresh_token = (
        "provider-reauth-refresh"
    )
    account_class.return_value.api.refresh_token = "provider-reauth-refresh"
    result = await hass.config_entries.flow.async_init(
        "clevertouch",
        context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=dict(entry.data),
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"password": "offline-password"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.state is ConfigEntryState.LOADED
    assert entry.title == "My heating"
    assert entry.data["model"] == provider
    assert entry.data["token"] == "provider-reauth-refresh"
    assert len(hass.config_entries.async_entries("clevertouch")) == 1
    assert session_class.call_args_list == [call(host=host, session=ANY)] * 2
    assert account_class.call_args_list == [
        call("offline@example.invalid", "provider-refresh", host=host, session=ANY),
        call(
            "offline@example.invalid", "provider-reauth-refresh", host=host, session=ANY
        ),
    ]
