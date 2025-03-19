"""Config flow for Clever Touch E3 integration."""

from __future__ import annotations

import logging
from typing import Any
import voluptuous as vol
from collections.abc import Mapping

from homeassistant.const import (
    CONF_TOKEN,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_MODEL,
)
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
    SelectSelector,
    SelectSelectorConfig,
    SelectOptionDict,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from clevertouch import ApiSession, ApiAuthError

from .const import DOMAIN, MODELS, DEFAULT_MODEL_ID

_LOGGER = logging.getLogger(__name__)

MODEL_LIST = [
    SelectOptionDict(value=key, label=f"{value.app} ({value.url})")
    for key, value in MODELS.items()
]

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_MODEL): SelectSelector(
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
    model_id = data.get(CONF_MODEL) or DEFAULT_MODEL_ID
    username = data.get(CONF_USERNAME)
    password = data.get(CONF_PASSWORD)

    model = MODELS[model_id]

    host = model.url

    if not username or not password:
        _LOGGER.debug("No username or password provided")
        raise InvalidAuth

    session = async_get_clientsession(hass)

    async with ApiSession(host=host, session=session) as api:
        try:
            await api.authenticate(username, password)
        except ApiAuthError as ex:
            raise InvalidAuth from ex
        except Exception as ex:
            raise CannotConnect from ex
        token = api.refresh_token

    return {
        "title": model.app,
        CONF_USERNAME: username,
        CONF_TOKEN: token,
        CONF_MODEL: model_id,
    }


class CleverTouchFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Clever Touch E3."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the Clever Touch E3 config flow."""
        super().__init__()
        self._model = None
        self._username = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        errors = {}

        username = user_input.get(CONF_USERNAME) or None
        if username:
            username = username.strip().lower()
            user_input[CONF_USERNAME] = username.lower()

            # Assign a unique ID to the flow and abort the flow
            # if another flow with the same unique ID is in progress
            await self.async_set_unique_id(username)

            # Abort the flow if a config entry with the same unique ID exists
            self._abort_if_unique_id_configured()

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

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Perform reauth upon an API authentication error."""
        _LOGGER.debug("Reauthenticating due to API authentication error")
        self._model = entry_data.get(CONF_MODEL)
        self._username = entry_data.get(CONF_USERNAME)

        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Dialog that informs the user that reauth is required."""
        errors = {}
        if user_input:
            user_input[CONF_MODEL] = self._model
            user_input[CONF_USERNAME] = self._username
            entry = await self.async_set_unique_id(self._username)

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
                return self.async_update_reload_and_abort(
                    entry, title=info["title"], data=info, unique_id=self._username
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(
                            type=TextSelectorType.PASSWORD,
                            autocomplete="current-password",
                        )
                    )
                }
            ),
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
