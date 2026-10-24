"""Fixtures for offline CleverTouch integration tests."""

import json
from pathlib import Path
from typing import Any

import pytest
from pytest_homeassistant.common import MockConfigEntry
from pytest_homeassistant.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)
from yarl import URL

from homeassistant.core import HomeAssistant


@pytest.fixture
def hass_config_dir(tmp_path: Path) -> str:
    """Expose the checkout as a custom integration in an isolated configuration."""
    components = tmp_path / "custom_components"
    components.mkdir()
    (components / "clevertouch").symlink_to(Path(__file__).resolve().parents[1])
    return str(tmp_path)


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Create an entry without any real account credentials."""
    entry = MockConfigEntry(
        domain="clevertouch",
        unique_id="offline@example.invalid",
        title="CleverTouch",
        data={
            "username": "offline@example.invalid",
            "token": "offline-refresh",
            "model": "purmo",
        },
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def home_data(order: int) -> list[dict[str, Any]]:
    """Load synthetic homes in the requested API discovery order."""
    homes = json.loads((Path(__file__).parent / "fixtures/homes.json").read_text())
    for home in homes:
        home["devices"] = home["devices"][::order]
    return homes[::order]


@pytest.fixture
def mock_api(
    aioclient_mock: AiohttpClientMocker, home_data: list[dict[str, Any]]
) -> None:
    """Mock token refresh and read endpoints; writes have no registered response."""
    aioclient_mock.post(
        "https://auth.e3.lvi.eu/realms/purmo/protocol/openid-connect/token",
        json={
            "access_token": "offline-access",
            "refresh_token": "offline-refresh",
            "expires_in": 3600,
        },
    )
    aioclient_mock.post(
        "https://e3.lvi.eu/api/v0.1/human/user/read/",
        json={
            "code": {"code": "1", "key": "ok", "value": "OK"},
            "data": {"user_id": "offline-user", "smarthomes": home_data},
        },
    )
    homes = {home["smarthome_id"]: home for home in home_data}

    async def read_home(
        method: str, url: URL, data: dict[str, str]
    ) -> AiohttpClientMockResponse:
        return AiohttpClientMockResponse(
            method=method,
            url=url,
            json={
                "code": {"code": "1", "key": "ok", "value": "OK"},
                "data": homes[data["smarthome_id"]],
            },
        )

    aioclient_mock.post(
        "https://e3.lvi.eu/api/v0.1/human/smarthome/read/", side_effect=read_home
    )
