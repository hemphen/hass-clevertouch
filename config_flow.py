"""Config flow for Clever Touch E3 integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from clevertouch import ApiSession, ApiAuthError, ApiConnectError

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("email"): str,
        vol.Required("password"): str,
    }
)


class ClevertouchHub:
    """Placeholder class to make tests pass.

    TODO Remove this placeholder class and replace with things from your PyPI package.
    """

    def __init__(self) -> None:
        self.session = None

    async def authenticate(self, email: str, password: str) -> bool:
        """Authenticates with the CleverTouch api"""
        if self.session is None:
            self.session = ApiSession(email)
        elif self.session.email != email:
            await self.session.close()
            self.session = ApiSession(email)
        await self.session.authenticate(email, password)
        return self.session.token is not None


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    hub = ClevertouchHub()

    try:
        if not await hub.authenticate(data["email"], data["password"]):
            raise InvalidAuth
    except ApiAuthError as ex:
        raise InvalidAuth from ex
    except ApiConnectError as ex:
        raise CannotConnect from ex

    if not hub.session or not hub.session.email or not hub.session.token:
        raise CannotConnect

    return {
        "title": "CleverTouch",
        "email": hub.session.email,
        "token": hub.session.token,
    }


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Clever Touch E3."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        errors = {}

        try:
            info = await validate_input(self.hass, user_input)
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"

        else:
            return self.async_create_entry(title=info["title"], data=info)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
