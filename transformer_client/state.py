from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from threading import RLock

from transformer_client.models import MeterDto, MeterStatus, RegisterControl, RegisterDto, RegisterState, TransformerDto


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
    target_value: float | None
    threshold_value: float | None
    control_active: bool
    unit: str | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class ActiveControlContext:
    meter_id: int
    register_id: int
    meter_name: str
    register_name: str
    current_value: float | None
    target_value: float | None
    threshold_value: float | None
    unit: str | None
    last_update: datetime | None


class ApplicationState:
    def __init__(self) -> None:
        self._lock = RLock()
        self._transformers: tuple[TransformerDto, ...] = ()
        self._selected_transformer: TransformerDto | None = None
        self._meters: dict[int, MeterDto] = {}
        self._registers_by_meter: dict[int, tuple[RegisterDto, ...]] = {}
        self._register_states: dict[tuple[int, int], RegisterState] = {}
        self._controls: dict[tuple[int, int], RegisterControl] = {}
        self._active_control_key: tuple[int, int] | None = None
        self._meter_statuses: dict[int, str] = {}
        self._meter_errors: dict[int, str | None] = {}
        self._last_backend_error: str | None = None
        self._motor_state: str = "IDLE"
        self._motor_direction: str = "STOPPED"
        self._motor_message: str = "Brak aktywnego rejestru."
        self._metrics_state: str = "DISCONNECTED"
        self._metrics_error: str | None = None
        self._metric_points: dict[tuple[str, str], dict] = {}

    def apply_configuration(
        self,
        transformers: list[TransformerDto],
        selected_transformer: TransformerDto,
        meters: list[MeterDto],
        registers_by_meter: dict[int, list[RegisterDto]],
        controls: dict[tuple[int, int], RegisterControl],
        active_control_key: tuple[int, int] | None,
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
            self._controls = {key: value for key, value in controls.items() if key in next_states}
            self._active_control_key = active_control_key if active_control_key in self._controls else None
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

    def set_register_control(
        self,
        meter_id: int,
        register_id: int,
        target_value: float | None,
        threshold_value: float | None,
        active: bool,
    ) -> None:
        with self._lock:
            key = (meter_id, register_id)
            register = self._find_register(key)
            if register is None:
                raise KeyError(f"Register {meter_id}:{register_id} not found.")

            updated = replace(register, targetValue=target_value, thresholdValue=threshold_value)
            self._replace_register(key, updated)
            self._controls[key] = RegisterControl(
                meterId=meter_id,
                registerId=register_id,
                targetValue=target_value,
                thresholdValue=threshold_value,
            )
            if active:
                self._active_control_key = key

    def clear_active_control(self) -> None:
        with self._lock:
            self._active_control_key = None

    def set_motor_state(self, state_name: str, direction: str, message: str) -> None:
        with self._lock:
            self._motor_state = state_name
            self._motor_direction = direction
            self._motor_message = message

    def set_metrics_state(self, state_name: str, error_message: str | None) -> None:
        with self._lock:
            self._metrics_state = state_name
            self._metrics_error = error_message

    def merge_metric_point(self, point: dict) -> None:
        key = point.get("key")
        bucket_ts = point.get("bucketTs")
        if not key or not bucket_ts:
            return
        with self._lock:
            self._metric_points[(str(key), str(bucket_ts))] = dict(point)

    def get_active_control_context(self) -> ActiveControlContext | None:
        with self._lock:
            if self._active_control_key is None:
                return None
            row = self._build_active_control_row()
            if row is None:
                return None
            return ActiveControlContext(
                meter_id=row.meter_id,
                register_id=row.register_id,
                meter_name=row.meter_name,
                register_name=row.register_name,
                current_value=row.value,
                target_value=row.target_value,
                threshold_value=row.threshold_value,
                unit=row.unit,
                last_update=row.updated_at,
            )

    def snapshot(self) -> dict:
        with self._lock:
            rows: list[UiRow] = []
            meters = sorted(self._meters.values(), key=lambda meter: (meter.serialPort, meter.name.lower(), meter.id))
            for meter in meters:
                status = self._meter_statuses.get(meter.id, MeterStatus.CONNECTING)
                error = self._meter_errors.get(meter.id)
                for register in self._registers_by_meter.get(meter.id, ()):
                    state = self._register_states.get((meter.id, register.id))
                    key = (meter.id, register.id)
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
                            target_value=register.targetValue,
                            threshold_value=register.thresholdValue,
                            control_active=key == self._active_control_key,
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
                "active_control_key": self._active_control_key,
                "motor_state": self._motor_state,
                "motor_direction": self._motor_direction,
                "motor_message": self._motor_message,
                "metrics_state": self._metrics_state,
                "metrics_error": self._metrics_error,
            }

    def metrics_payload(self, transformer_id: str) -> dict:
        with self._lock:
            metrics: list[dict] = []
            for meter in sorted(self._meters.values(), key=lambda meter: meter.id):
                meter_status = self._meter_statuses.get(meter.id, MeterStatus.CONNECTING)
                for register in self._registers_by_meter.get(meter.id, ()):
                    state = self._register_states.get((meter.id, register.id))
                    if state is None or state.value is None or state.lastUpdate is None:
                        continue
                    metrics.append(
                        {
                            "meterId": meter.id,
                            "meterName": meter.name,
                            "meterStatus": meter_status,
                            "registerId": register.id,
                            "registerName": register.name,
                            "registerType": register.registerType,
                            "address": register.address,
                            "dataType": register.dataType,
                            "unit": register.unit,
                            "value": state.value,
                            "lastUpdate": state.lastUpdate.isoformat(),
                        }
                    )
            return {
                "type": "transformer_metrics",
                "transformerId": transformer_id,
                "sentAt": datetime.now().isoformat(),
                "metrics": metrics,
            }

    def metrics_messages(self) -> list[dict]:
        with self._lock:
            messages: list[dict] = []
            for meter in sorted(self._meters.values(), key=lambda item: item.id):
                for register in self._registers_by_meter.get(meter.id, ()):
                    state = self._register_states.get((meter.id, register.id))
                    if state is None or state.value is None or state.lastUpdate is None:
                        continue
                    key = f"{meter.deviceCode}.{register.name}" if meter.deviceCode else register.name
                    label = f"{meter.name} / {register.name}"
                    messages.append(
                        {
                            "metricKey": key,
                            "value": state.value,
                            "timestamp": state.lastUpdate,
                            "unit": register.unit,
                            "label": label,
                        }
                    )
            return messages

    def _find_register(self, key: tuple[int, int]) -> RegisterDto | None:
        meter_id, register_id = key
        for register in self._registers_by_meter.get(meter_id, ()):
            if register.id == register_id:
                return register
        return None

    def _replace_register(self, key: tuple[int, int], updated: RegisterDto) -> None:
        meter_id, register_id = key
        registers = list(self._registers_by_meter.get(meter_id, ()))
        for index, register in enumerate(registers):
            if register.id == register_id:
                registers[index] = updated
                self._registers_by_meter[meter_id] = tuple(registers)
                break
        state = self._register_states.get(key)
        if state is not None:
            state.register = updated

    def _build_active_control_row(self) -> UiRow | None:
        if self._active_control_key is None:
            return None
        meter_id, register_id = self._active_control_key
        meter = self._meters.get(meter_id)
        register = self._find_register((meter_id, register_id))
        if meter is None or register is None:
            return None
        state = self._register_states.get((meter_id, register_id))
        status = self._meter_statuses.get(meter_id, MeterStatus.CONNECTING)
        error = self._meter_errors.get(meter_id)
        return UiRow(
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
            target_value=register.targetValue,
            threshold_value=register.thresholdValue,
            control_active=True,
            unit=register.unit,
            updated_at=state.lastUpdate if state else None,
        )


def _sort_registers(registers: list[RegisterDto]) -> list[RegisterDto]:
    return sorted(
        registers,
        key=lambda register: (
            register.orderIndex if register.orderIndex is not None else 2**31,
            register.address,
            register.id,
        ),
    )
