from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from threading import RLock

from transformer_client.models import MeterDto, MeterStatus, RegisterDto, RegisterState, TransformerDto


@dataclass(frozen=True, slots=True)
class UiRow:
    meter_id: int
    meter_name: str
    serial_port: str
    status: str
    error: str | None
    register_id: int
    register_name: str
    register_type: str
    address: int
    data_type: str
    value: float | None
    unit: str | None
    updated_at: datetime | None


class ApplicationState:
    def __init__(self) -> None:
        self._lock = RLock()
        self._transformers: tuple[TransformerDto, ...] = ()
        self._selected_transformer: TransformerDto | None = None
        self._meters: dict[int, MeterDto] = {}
        self._registers_by_meter: dict[int, tuple[RegisterDto, ...]] = {}
        self._register_states: dict[tuple[int, int], RegisterState] = {}
        self._meter_statuses: dict[int, str] = {}
        self._meter_errors: dict[int, str | None] = {}
        self._last_backend_error: str | None = None

    def apply_configuration(
        self,
        transformers: list[TransformerDto],
        selected_transformer: TransformerDto,
        meters: list[MeterDto],
        registers_by_meter: dict[int, list[RegisterDto]],
    ) -> None:
        with self._lock:
            self._transformers = tuple(transformers)
            self._selected_transformer = selected_transformer
            self._meters = {meter.id: meter for meter in meters}
            self._registers_by_meter = {
                meter_id: tuple(_sort_registers(registers))
                for meter_id, registers in registers_by_meter.items()
            }

            next_states: dict[tuple[int, int], RegisterState] = {}
            for meter_id, registers in self._registers_by_meter.items():
                for register in registers:
                    key = (meter_id, register.id)
                    existing = self._register_states.get(key)
                    next_states[key] = existing or RegisterState(meterId=meter_id, register=register)
                    if existing is not None:
                        existing.register = register
            self._register_states = next_states
            self._meter_statuses = {
                meter.id: self._meter_statuses.get(meter.id, MeterStatus.CONNECTING)
                for meter in meters
            }
            self._meter_errors = {meter.id: self._meter_errors.get(meter.id) for meter in meters}
            self._last_backend_error = None

    def set_meter_status(self, meter_id: int, status: str, error_message: str | None = None) -> None:
        with self._lock:
            if meter_id not in self._meters:
                return
            self._meter_statuses[meter_id] = status
            self._meter_errors[meter_id] = error_message

    def set_all_meter_statuses(self, meter_ids: list[int], status: str, error_message: str | None = None) -> None:
        with self._lock:
            for meter_id in meter_ids:
                if meter_id in self._meters:
                    self._meter_statuses[meter_id] = status
                    self._meter_errors[meter_id] = error_message

    def update_register_value(self, meter_id: int, register: RegisterDto, value: float) -> None:
        with self._lock:
            key = (meter_id, register.id)
            state = self._register_states.get(key)
            if state is None:
                state = RegisterState(meterId=meter_id, register=register)
                self._register_states[key] = state
            state.register = register
            state.value = value
            state.lastUpdate = datetime.now()

    def set_backend_error(self, message: str | None) -> None:
        with self._lock:
            self._last_backend_error = message

    def snapshot(self) -> dict:
        with self._lock:
            rows: list[UiRow] = []
            meters = sorted(self._meters.values(), key=lambda meter: (meter.serialPort, meter.name.lower(), meter.id))
            for meter in meters:
                status = self._meter_statuses.get(meter.id, MeterStatus.CONNECTING)
                error = self._meter_errors.get(meter.id)
                for register in self._registers_by_meter.get(meter.id, ()):
                    state = self._register_states.get((meter.id, register.id))
                    rows.append(
                        UiRow(
                            meter_id=meter.id,
                            meter_name=meter.name,
                            serial_port=meter.serialPort,
                            status=status,
                            error=error,
                            register_id=register.id,
                            register_name=register.name,
                            register_type=register.registerType,
                            address=register.address,
                            data_type=register.dataType,
                            value=state.value if state else None,
                            unit=register.unit,
                            updated_at=state.lastUpdate if state else None,
                        )
                    )

            return {
                "transformers": list(self._transformers),
                "selected_transformer": self._selected_transformer,
                "rows": rows,
                "backend_error": self._last_backend_error,
                "meter_count": len(self._meters),
                "register_count": len(rows),
            }


def _sort_registers(registers: list[RegisterDto]) -> list[RegisterDto]:
    return sorted(
        registers,
        key=lambda register: (
            register.orderIndex if register.orderIndex is not None else 2**31,
            register.address,
            register.id,
        ),
    )
