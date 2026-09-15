"""Pure data handling for the Growatt ShineX D-Bus service."""

import math
from dataclasses import dataclass
from typing import Any, Mapping, Optional


def _number(value: Any, default: float = 0.0) -> float:
    """Convert a ShineX value to float without leaking NaN or negatives."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default

    if not math.isfinite(number):
        return default
    return max(number, 0.0)


def _optional_number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


def _integer(value: Any, default: int = 0) -> int:
    try:
        number = float(value)
        if not math.isfinite(number):
            return default
        return int(number)
    except (TypeError, ValueError, OverflowError):
        return default


def _running(value: Any, output_power: float) -> bool:
    if value is None:
        return output_power > 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "on", "online", "running"}
    return bool(_integer(value))


@dataclass(frozen=True)
class Measurement:
    serial: str
    inverter_running: bool
    power: float
    energy: Optional[float]
    voltage: float
    current: float
    error_code: int


def parse_measurement(payload: Mapping[str, Any]) -> Measurement:
    """Translate an OpenInverterGateway /status response to one L1 sample.

    ``OutputPower`` is the inverter's total real AC output and is authoritative
    for this single-phase driver. The L1 power register is only a fallback for
    firmware variants that omit ``OutputPower``.
    """
    if not isinstance(payload, Mapping):
        raise ValueError("ShineX response must be a JSON object")

    known_fields = {
        "InverterStatus",
        "OutputPower",
        "L1ThreePhaseGridOutputPower",
        "L1ThreePhaseGridVoltage",
        "TotalGenerateEnergy",
    }
    if not any(field in payload for field in known_fields):
        raise ValueError("ShineX response contains no recognised inverter fields")

    power_value = _optional_number(payload.get("OutputPower"))
    if power_value is None:
        power_value = _optional_number(payload.get("L1ThreePhaseGridOutputPower"))
    power = 0.0 if power_value is None else power_value

    voltage = _number(payload.get("L1ThreePhaseGridVoltage"))
    current = _number(payload.get("L1ThreePhaseGridOutputCurrent"))
    running = _running(payload.get("InverterStatus"), power)

    if not running:
        power = 0.0
        current = 0.0
    elif power > 0 and current <= 0.5 and voltage > 0:
        # Growatt reports AC current with coarse resolution at low output. Below
        # 0.5 A this can even make P > V * I, so derive a plausible current.
        current = power / voltage

    energy = _optional_number(payload.get("TotalGenerateEnergy"))

    serial = str(payload.get("Mac") or payload.get("mac") or "")
    serial = serial.replace(":", "").replace("-", "").strip().upper()

    return Measurement(
        serial=serial,
        inverter_running=running,
        power=power,
        energy=energy,
        voltage=voltage,
        current=current,
        error_code=_integer(payload.get("ErrorCode")),
    )
