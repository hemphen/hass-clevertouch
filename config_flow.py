"""Config flow for Clever Touch E3 integration."""
from __future__ import annotations

import logging
from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import (
    CONF_TOKEN,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_EMAIL,
    CONF_MODEL,
    CONF_HOST,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
    SelectSelector,
    SelectSelectorConfig,
    SelectOptionDict,
)

from clevertouch import ApiSession, ApiAuthError

from .const import DOMAIN, MODELS

_LOGGER = logging.getLogger(__name__)

MODEL_LIST = [
    SelectOptionDict(value=key, label=f"{value.app} ({value.url})")
    for key, value in MODELS.items()
]

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): SelectSelector(
            SelectSelectorConfig(options=MODEL_LIST)
        ),
        vol.Required(CONF_USERNAME): TextSelector(
            TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")
        ),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(
                type=TextSelectorType.PASSWORD, autocomplete="current-password"
            )
        ),
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    model_id = data.get(CONF_HOST) or "purmo"
    username = data.get(CONF_USERNAME) or data.get(CONF_EMAIL)
    password = data.get(CONF_PASSWORD)

    model = MODELS[model_id]

    host = model.url

    if not username or not password:
        raise InvalidAuth

    async with ApiSession(host=host) as session:
        try:
            await session.authenticate(username, password)
        except ApiAuthError as ex:
            raise InvalidAuth from ex
        except Exception as ex:
            raise CannotConnect from ex
        token = session.refresh_token

    return {
        "title": model.app,
        CONF_USERNAME: username,
        CONF_TOKEN: token,
        CONF_MODEL: model_id,
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
