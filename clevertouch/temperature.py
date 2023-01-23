from typing import Optional


class Temperature:
    DEVICE = ""
    CELSIUS = "c"
    FARENHEIT = "f"

    def __init__(
        self,
        temperature: float,
        unit: str = DEVICE,
        is_writable: bool = False,
        name: Optional[str] = None,
    ) -> None:
        self.name: Optional[str] = name
        self.is_writable: bool = is_writable

        if unit == Temperature.CELSIUS:
            device_temperature = round(18 * temperature + 320)
        elif unit == Temperature.FARENHEIT:
            device_temperature = round(10 * temperature)
        elif unit == Temperature.DEVICE:
            device_temperature = round(temperature)
        else:
            raise Exception("Unknown unit")

        self.device: float = device_temperature
        self.celsius: float = (device_temperature - 320) / 18
        self.farenheit: float = device_temperature / 10

    def as_unit(self, unit: str) -> str:
        if unit == Temperature.CELSIUS:
            return self.celsius
        elif unit == Temperature.FARENHEIT:
            return self.farenheit
        elif unit == Temperature.DEVICE:
            return self.device
        raise Exception(f"Unknown unit '{unit}'")

    @classmethod
    def convert(temperature: float, from_unit: str, to_unit: str) -> float:
        return Temperature(temperature, from_unit).as_unit(to_unit)

    @classmethod
    def from_celsius(cls, temperature: float):
        return Temperature(temperature, Temperature.CELSIUS)

    @classmethod
    def from_farenheit(cls, temperature: float):
        return Temperature(temperature, Temperature.FARENHEIT)

    @classmethod
    def from_device(cls, temperature: float):
        return Temperature(temperature, Temperature.DEVICE)
