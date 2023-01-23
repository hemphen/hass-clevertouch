"""Provides basic functionality for communicating with the CleverTouch account"""
from __future__ import annotations

from aiohttp import ClientSession
from typing import Optional, NamedTuple, Any
from hashlib import md5

from .util import AppException
from .temperature import Temperature


class ApiStatus(NamedTuple):
    code: int
    key: str
    value: str


class ApiResult(NamedTuple):
    status: ApiStatus
    data: dict[str, Any]
    parameters: dict[str, Any]


class ApiException(AppException):
    def __init__(self, status: ApiStatus, *args):
        super().__init__(*args)
        self.status: ApiStatus


class ApiAuthException(ApiException):
    pass


class ApiSession:
    API_LANG = "en_GB"
    API_BASE = "https://e3.lvi.eu"
    API_PATH = "/api/v0.1/"

    def __init__(
        self, email: Optional[str] = None, token: Optional[str] = None
    ) -> None:
        self._http_session = ClientSession(self.API_BASE)
        self.email: Optional[str] = email
        self.token: Optional[str] = token
        self.user: Optional[UserInfo] = None
        self.homes: dict[str, SmartHome] = {}

    async def authenticate(
        self,
        email: str,
        password: Optional[str] = None,
        password_hash: Optional[str] = None,
    ):
        if password_hash in [None, ""]:
            if password in [None, ""]:
                raise AppException("No password provided")
            password_hash = md5(password.encode()).hexdigest().encode().decode()

        endpoint = "human/user/auth/"
        payload = {
            "email": email,
            "password": password_hash,
            "remember_me": "true",
            "lang": self.API_LANG,
        }

        try:
            result = await self._api_post(endpoint, payload)
        except ApiException as ex:
            if ex.status.key == "ERR_PARAM":
                raise ApiAuthException(ex.status, "Invalid email or password") from ex
            raise ApiAuthException(
                ex.status, f"{ex.status.key}: {ex.status.value}"
            ) from ex

        self.email = result.data["user_infos"]["email"]
        self.token = result.data["token"]

    async def get_user(self) -> UserInfo:
        user = self.user
        if user is None:
            user = UserInfo(self, self.email)
            await user.refresh()
        return user

    async def get_home(self, home_id: str) -> SmartHome:
        home = self.homes.get(home_id)
        if home is None:
            home = SmartHome(self, home_id)
            await home.refresh()
        return home

    async def api_read(self, endpoint: str, payload: dict) -> ApiResult:
        payload.update(
            {
                "token": self.token,
                "lang": self.API_LANG,
            }
        )
        result = await self._api_post(endpoint, payload)
        if result.status.code != 1:
            raise ApiException(
                result.status.code,
                result.status.key,
                result.status.value,
                f"API read failed with status {result.status.key} ({result.status.code}): {result.status.value}",
            )
        return result

    async def api_write(self, endpoint: str, payload: dict) -> ApiResult:
        payload.update(
            {
                "token": self.token,
                "lang": self.API_LANG,
            }
        )
        result = await self._api_post(endpoint, payload)
        if result.status.code != 8:
            raise ApiException(
                result.status.code,
                result.status.key,
                result.status.value,
                f"API write failed with status {result.status.key} ({result.status.code}): {result. status.value}",
            )
        return result

    def _parse_api_json(self, json: dict) -> ApiResult:
        try:
            code = json["code"]
            data = json["data"]
            parameters = json["parameters"]
        except Exception as ex:
            raise AppException("Unexpected JSON format in API response") from ex

        try:
            code_num = int(code["code"])
            code_key = code["key"]
            code_value = code["value"]
            status = ApiStatus(code_num, code_key, code_value)
        except Exception as ex:
            raise AppException("API status is malformed") from ex

        return ApiResult(status, data, parameters)

    async def _api_post(self, endpoint: str, payload: dict) -> ApiResult:
        async with self._http_session.post(
            self.API_PATH + endpoint, data=payload
        ) as response:
            response.raise_for_status()
            json_data = await response.json()

        return self._parse_api_json(json_data)


class SmartHome:
    def __init__(self, session: ApiSession, home_id: str) -> None:
        self._session = session
        self.home_id: str = home_id
        self.label: Optional[str] = None
        self.zones: dict[str, ZoneInfo] = {}
        self.devices: dict[str, Device] = {}

    def _update(self, data):
        self.home_id = data["smarthome_id"]
        self.label = data["label"]

        self.zones |= {
            zone.id_local: zone
            for zone in [
                self.zones.get(zone_data["num_zone"], ZoneInfo(zone_data))
                for zone_data in data["zones"].values()
            ]
        }
        self.devices |= {
            device.device_id: device
            for device in [
                self._update_or_create_device(device_data)
                for device_data in data["devices"].values()
            ]
        }

    def _update_or_create_device(self, data: dict[str, Any]) -> Device:
        device = self.devices.get(data["id"])
        if device is None:
            device = Device.create_device(self, data)
        else:
            device.update(data)
        return device

    async def refresh(self) -> None:
        endpoint = "human/smarthome/read/"
        payload = {
            "smarthome_id": self.home_id,
        }
        _, data, _ = await self._session.api_read(endpoint, payload)
        self._update(data)

    async def write(self, query_params):
        endpoint = "human/query/push/"
        payload = {
            "smarthome_id": self.home_id,
            "context": 1,
            "peremption": 15000,
        }
        for key, value in query_params.items():
            payload[f"query[{key}]"] = value

        return await self._session.api_write(endpoint, payload)


class UserInfo:
    def __init__(self, session: ApiSession, email: str) -> None:
        self._session = session
        self.user_id: Optional[str] = None
        self.email: Optional[str] = email
        self.homes: dict[str, SmartHomeInfo] = {}

    async def refresh(self):
        endpoint = "human/user/read/"
        payload = {
            "email": self._session.email,
        }
        _, data, _ = await self._session.api_read(endpoint, payload)
        self._update(data)

    def _update(self, data):
        self.user_id = data["user_id"]
        self.homes |= {
            home.home_id: home
            for home in [
                self.homes.get(home_data["smarthome_id"], SmartHomeInfo(home_data))
                for home_data in data["smarthomes"].values()
            ]
        }


class SmartHomeInfo:
    def __init__(self, data: dict[str, Any]) -> None:
        self.home_id = data["smarthome_id"]
        self.label = data["label"]
        self._update(data)

    def _update(self, data: dict[str, Any]):
        self.label = data["label"]


class ZoneInfo:
    def __init__(self, data: dict) -> None:
        self.id_local: str = data["num_zone"]
        self._update(data)

    def _update(self, data: dict[str, Any]):
        self.label: str = data["zone_label"]


class Device:
    DEVICE_RADIATOR = "Radiator"
    DEVICE_LIGHT = "Light"
    DEVICE_OUTLET = "Outlet"
    DEVICE_UNKNOWN = "Unknown"

    def __init__(self, home: SmartHome, data: dict[str, Any], device_type: str) -> None:
        self.type: str = device_type
        self.home: SmartHome = home
        self.device_id: str = data["id"]
        self.update(data)

    def update(self, data: dict[str, Any]):
        self.zone_id = data["num_zone"]
        self.id_local: str = data["id_device"]
        self.label: str = data["label_interface"]

    @property
    def zone(self) -> ZoneInfo:
        return self.home.zones[self.zone_id]

    @classmethod
    def create_device(cls, home: SmartHome, data: dict[str, Any]) -> Device:
        nv_mode = data["nv_mode"]
        if nv_mode == "0":
            return Radiator(home, data)
        elif nv_mode == "1":
            return Light(home, data)
        elif nv_mode == "12":
            return Outlet(home, data)
        else:
            return Device(home, data, Device.DEVICE_UNKNOWN)


class _ModeInfo(NamedTuple):
    heat_mode: str
    temp_mode: Optional[str]


MODE_ECO = "eco"
MODE_FROST = "frost"
MODE_COMFORT = "comfort"
MODE_PROGRAM = "program"
MODE_OFF = "off"
MODE_BOOST = "boost"

TEMP_ECO = "eco"
TEMP_FROST = "frost"
TEMP_COMFORT = "comfort"
TEMP_CURRENT = "current"
TEMP_MANUAL = "manual"
TEMP_BOOST = "boost"
TEMP_TARGET = "target"


class Radiator(Device):
    _MODE_TYPES = {
        "0": _ModeInfo(MODE_COMFORT, TEMP_COMFORT),
        "1": _ModeInfo(MODE_OFF, None),
        "2": _ModeInfo(MODE_COMFORT, TEMP_FROST),
        "3": _ModeInfo(MODE_ECO, TEMP_ECO),
        "4": _ModeInfo(MODE_BOOST, TEMP_BOOST),
        # "5": ModeInfo("fan", None),
        # "6": ModeInfo("fan-disabled", None),
        "8": _ModeInfo(MODE_PROGRAM, TEMP_COMFORT),
        "11": _ModeInfo(MODE_PROGRAM, TEMP_ECO),
        # "13": ModeInfo("program", None),
        # "15": ModeInfo("manual", "manual"),
        # "16": ModeInfo("program", "boost"),
    }

    _MODE_MAP = {
        MODE_ECO: "3",
        MODE_FROST: "2",
        MODE_COMFORT: "0",
        MODE_PROGRAM: "11",
        MODE_OFF: "1",
    }

    _TEMP_MAP = {
        TEMP_ECO: "consigne_eco",
        TEMP_FROST: "consigne_hg",
        TEMP_COMFORT: "consigne_confort",
        TEMP_CURRENT: "temperature_air",
        TEMP_MANUAL: "consigne_manuel",
        TEMP_BOOST: "consigne_boost",
    }

    _TEMPS_AVAILABLE = [TEMP_ECO, TEMP_FROST, TEMP_COMFORT, TEMP_CURRENT, TEMP_BOOST]
    _TEMPS_READONLY = [TEMP_CURRENT, TEMP_TARGET, TEMP_BOOST]
    _MODES_AVAILABLE = [MODE_ECO, MODE_FROST, MODE_PROGRAM, MODE_OFF]

    def __init__(self, home: SmartHome, data: dict) -> None:
        super().__init__(home, data, Device.DEVICE_RADIATOR)
        self.modes: list[str] = self._MODES_AVAILABLE

    def update(self, data: dict[str, Any]):
        super().update(data)
        self.mode_num: str = data["gv_mode"]
        self._program_type: _ModeInfo = self._MODE_TYPES[self.mode_num]
        self.time_boost: int = int(data["time_boost"])
        self.active: bool = data["heating_up"] == "1"
        self.heat_mode: str = self._program_type.heat_mode
        self.temp_mode: str = self._program_type.temp_mode
        self.temperatures: dict[str, Temperature] = {
            temp: Temperature(
                int(data[self._TEMP_MAP[temp]]),
                is_writable=temp not in self._TEMPS_READONLY,
                name=temp,
            )
            for temp in self._TEMPS_AVAILABLE
        }
        self.temperatures[TEMP_TARGET] = Temperature(
            None
            if self.temp_mode is None
            else self.temperatures[self.temp_mode].device,
            is_writable=False,
            name=TEMP_TARGET,
        )

    async def set_temperature(self, temp_type: str, temp_value: int, unit: str):
        query_params = {}
        query_params["id_device"] = self.id_local
        query_params[self._TEMP_MAP[temp_type]] = Temperature(temp_value, unit).device

        await self.home.write(query_params)

    async def set_mode(self, heat_mode: str):
        query_params = {}
        query_params["id_device"] = self.id_local
        query_params["gv_mode"] = self._MODE_MAP[heat_mode]
        query_params["nv_mode"] = self._MODE_MAP[heat_mode]

        await self.home.write(query_params)


class Light(Device):
    def __init__(self, home: SmartHome, data: dict[str, Any]) -> None:
        super().__init__(home, data, Device.DEVICE_LIGHT)


class Outlet(Device):
    def __init__(self, home: SmartHome, data: dict[str, Any]) -> None:
        super().__init__(home, data, Device.DEVICE_OUTLET)
