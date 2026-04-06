from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from transformer_client.modbus import ModbusError, ModbusTransportError, SerialModbusClient, SerialPortConfig
from transformer_client.models import ClientConfig, MeterDto, MeterStatus, RegisterDto
from transformer_client.state import ApplicationState


@dataclass(slots=True)
class PortGroup:
    serial_port: str
    meters: tuple[MeterDto, ...]
    registers_by_meter: dict[int, tuple[RegisterDto, ...]]
    client_config: ClientConfig

    def signature(self) -> tuple:
        return (
            self.serial_port,
            tuple(
                (
                    meter.id,
                    meter.serialPort,
                    meter.baudRate,
                    meter.dataBits,
                    meter.stopBits,
                    meter.parity,
                    meter.slaveId,
                    meter.byteOrder,
                    meter.pollIntervalMs,
                )
                for meter in self.meters
            ),
            tuple(
                (
                    meter_id,
                    tuple(
                        (
                            register.id,
                            register.registerType,
                            register.address,
                            register.length,
                            register.dataType,
                            register.scale,
                            register.orderIndex,
                        )
                        for register in self.registers_by_meter.get(meter_id, ())
                    ),
                )
                for meter_id in sorted(self.registers_by_meter)
            ),
            self.client_config.pollIntervalMs,
            self.client_config.reconnectDelayMs,
            self.client_config.modbusTimeoutMs,
            self.client_config.modbusRetries,
            self.client_config.modbusDiscardDelayMs,
            self.client_config.interRegisterDelayMs,
        )

    def validate(self) -> str | None:
        if not self.meters:
            return "No enabled meters for this serial port."
        baseline = self.meters[0]
        for meter in self.meters[1:]:
            if (
                meter.baudRate != baseline.baudRate
                or meter.dataBits != baseline.dataBits
                or meter.stopBits != baseline.stopBits
                or meter.parity.upper() != baseline.parity.upper()
            ):
                return (
                    f"Conflicting serial settings on {self.serial_port}. "
                    "Meters sharing one port must use identical baudRate, dataBits, stopBits and parity."
                )
        return None

    def port_config(self) -> SerialPortConfig:
        meter = self.meters[0]
        return SerialPortConfig(
            port_name=self.serial_port,
            baud_rate=meter.baudRate,
            data_bits=meter.dataBits,
            parity=meter.parity,
            stop_bits=meter.stopBits,
        )

    def effective_delay_ms(self) -> int:
        backend_delays = [meter.pollIntervalMs for meter in self.meters if meter.pollIntervalMs and meter.pollIntervalMs > 0]
        if backend_delays:
            return min(self.client_config.pollIntervalMs, min(backend_delays))
        return self.client_config.pollIntervalMs


class PortPollingWorker(threading.Thread):
    def __init__(self, group: PortGroup, state: ApplicationState) -> None:
        super().__init__(daemon=True, name=f"poll-{group.serial_port}")
        self.group = group
        self.state = state
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        meter_ids = [meter.id for meter in self.group.meters]
        while not self._stop_event.is_set():
            validation_error = self.group.validate()
            if validation_error:
                self.state.set_all_meter_statuses(meter_ids, MeterStatus.ERROR, validation_error)
                self._wait(self.group.client_config.reconnectDelayMs)
                continue

            self.state.set_all_meter_statuses(meter_ids, MeterStatus.CONNECTING)
            client = SerialModbusClient(
                self.group.port_config(),
                timeout_ms=self.group.client_config.modbusTimeoutMs,
                retries=self.group.client_config.modbusRetries,
                discard_delay_ms=self.group.client_config.modbusDiscardDelayMs,
            )

            try:
                client.open()
                self.state.set_all_meter_statuses(meter_ids, MeterStatus.CONNECTED)
                self._poll_loop(client)
            except Exception as exc:
                self.state.set_all_meter_statuses(meter_ids, MeterStatus.ERROR, str(exc))
                self._wait(self.group.client_config.reconnectDelayMs)
            finally:
                client.close()

    def _poll_loop(self, client: SerialModbusClient) -> None:
        while not self._stop_event.is_set():
            cycle_started = time.monotonic()
            try:
                for meter in self.group.meters:
                    self.state.set_meter_status(meter.id, MeterStatus.CONNECTED)
                    registers = self.group.registers_by_meter.get(meter.id, ())
                    for register in registers:
                        value = client.read_value(meter, register)
                        self.state.update_register_value(meter.id, register, value)
                        self.state.set_meter_status(meter.id, MeterStatus.CONNECTED)
                        if self.group.client_config.interRegisterDelayMs > 0:
                            self._wait(self.group.client_config.interRegisterDelayMs)
            except ModbusTransportError as exc:
                self.state.set_all_meter_statuses(
                    [meter.id for meter in self.group.meters],
                    MeterStatus.ERROR,
                    str(exc),
                )
                raise
            except ModbusError as exc:
                self.state.set_all_meter_statuses(
                    [meter.id for meter in self.group.meters],
                    MeterStatus.ERROR,
                    str(exc),
                )

            elapsed_ms = int((time.monotonic() - cycle_started) * 1000)
            effective_delay = self.group.effective_delay_ms()
            remaining = effective_delay - elapsed_ms
            if remaining > 0:
                self._wait(remaining)

    def _wait(self, duration_ms: int) -> None:
        deadline = time.monotonic() + max(duration_ms, 0) / 1000.0
        while not self._stop_event.is_set() and time.monotonic() < deadline:
            time.sleep(0.05)


class PollingSupervisor:
    def __init__(self, state: ApplicationState) -> None:
        self.state = state
        self._lock = threading.RLock()
        self._workers: dict[str, PortPollingWorker] = {}

    def reconcile(
        self,
        meters: list[MeterDto],
        registers_by_meter: dict[int, list[RegisterDto]],
        client_config: ClientConfig,
    ) -> None:
        desired_groups = build_port_groups(meters, registers_by_meter, client_config)
        with self._lock:
            existing_ports = set(self._workers)
            desired_ports = set(desired_groups)

            for serial_port in existing_ports - desired_ports:
                worker = self._workers.pop(serial_port)
                worker.stop()
                worker.join(timeout=1.0)

            for serial_port, group in desired_groups.items():
                existing = self._workers.get(serial_port)
                if existing is not None and existing.group.signature() == group.signature():
                    continue
                if existing is not None:
                    existing.stop()
                    existing.join(timeout=1.0)
                worker = PortPollingWorker(group, self.state)
                self._workers[serial_port] = worker
                worker.start()

    def shutdown(self) -> None:
        with self._lock:
            workers = list(self._workers.values())
            self._workers.clear()
        for worker in workers:
            worker.stop()
        for worker in workers:
            worker.join(timeout=1.0)


def build_port_groups(
    meters: list[MeterDto],
    registers_by_meter: dict[int, list[RegisterDto]],
    client_config: ClientConfig,
) -> dict[str, PortGroup]:
    grouped: dict[str, list[MeterDto]] = {}
    for meter in meters:
        grouped.setdefault(meter.serialPort, []).append(meter)

    result: dict[str, PortGroup] = {}
    for serial_port, port_meters in grouped.items():
        ordered_meters = tuple(sorted(port_meters, key=lambda meter: meter.id))
        result[serial_port] = PortGroup(
            serial_port=serial_port,
            meters=ordered_meters,
            registers_by_meter={
                meter.id: tuple(registers_by_meter.get(meter.id, ()))
                for meter in ordered_meters
            },
            client_config=client_config,
        )
    return result
